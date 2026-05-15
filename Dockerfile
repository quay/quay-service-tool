### --- Frontend build --- ###

FROM registry.redhat.io/ubi9/nodejs-22@sha256:e06a0042a0a1502696a6f139f50e7fc1048a38d9c8358747c36d8905bf3f9258 AS frontend-base

ENV APP_ROOT=/frontend \
    HOME=/frontend \
    PLATFORM="el8" \
    NODEJS_VERSION=22 \
    NAME=nodejs

COPY --chown=1001:0 ./frontend /frontend

RUN chmod -R ug+rwx /frontend
WORKDIR "$HOME"
USER 1001

RUN npm install --legacy-peer-deps

FROM frontend-base AS frontend-dev
EXPOSE 9000
CMD ["npm", "run", "start:dev"]

FROM frontend-base AS frontend-build
RUN npm run build


### --- Backend --- ###

FROM registry.access.redhat.com/ubi9/python-312:latest@sha256:ff373f4b42b662e99954adea770ca87b4ea963186cc752174ccb94aa08fa702d AS backend-base

ENV SERVICETOOLDIR=/backend

COPY --from=ghcr.io/astral-sh/uv:0.11.11@sha256:798712e57f879c5393777cbda2bb309b29fcdeb0532129d4b1c3125c5385975a /uv /bin/uv

COPY --chown=1001:0 ./backend /backend

RUN chmod -R ug+rwx $SERVICETOOLDIR

USER root

ENV TZ=UTC
RUN set -ex\
	; dnf update -y \
	; dnf -y --setopt=tsflags=nodocs install \
	gcc-c++ \
	git \
	openldap-devel \
	libffi-devel \
	openssl-devel \
	diffutils \
	file \
	make \
	libjpeg-turbo \
	libjpeg-turbo-devel \
	freetype-devel \
	libxml2-devel \
	libxslt-devel \
	; dnf -y clean all && rm -rf /var/cache/yum

USER 1001

ENV UV_COMPILE_BYTECODE=true \
    UV_NO_CACHE=true \
    UV_PYTHON=3.12

WORKDIR "$SERVICETOOLDIR"
RUN uv sync --frozen --no-dev

ENV PATH="$SERVICETOOLDIR/.venv/bin:$PATH"

FROM backend-base AS backend-dev
EXPOSE 5000
ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0:5000", "--limit-request-field_size", "16384", "--reload", "app:app"]

FROM backend-base AS production

ENV SERVICETOOL_RUN=/conf

COPY --chown=1001:0 ./conf /conf
COPY --from=frontend-build --chown=1001:0 /frontend/dist /backend/static

RUN chmod -R ug+rwx $SERVICETOOL_RUN

EXPOSE 5000

ENTRYPOINT ["dumb-init", "--", "/conf/entrypoint.sh"]
