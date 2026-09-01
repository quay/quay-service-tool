### --- Frontend build --- ###

FROM registry.redhat.io/ubi9/nodejs-22@sha256:57ad03c5db9382cd266af665819f60e5b1490fc27ee589320159df59f9eb453b AS frontend-base

ENV APP_ROOT=/frontend \
    HOME=/frontend \
    PLATFORM="el8" \
    NODEJS_VERSION=22 \
    NAME=nodejs

COPY --chown=1001:0 ./frontend /frontend

RUN chmod -R ug+rwx /frontend
WORKDIR "$HOME"
USER 1001

RUN npm install -g pnpm@11 && pnpm install --frozen-lockfile

FROM frontend-base AS frontend-dev
EXPOSE 9000
CMD ["pnpm", "start:dev"]

FROM frontend-base AS frontend-build
RUN pnpm build


### --- Backend --- ###

FROM registry.access.redhat.com/ubi9/python-312:latest@sha256:aebe03384391689993c42998836597e6161ac5340cbc84518c1b0528a1c59ea8 AS backend-base

ENV SERVICETOOLDIR=/backend

COPY --from=ghcr.io/astral-sh/uv:0.12.7@sha256:95f2aa1fe59274951cfe9b0cbc7972e879ff1004bc8945d130a32eb0dbd85945 /uv /bin/uv

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
