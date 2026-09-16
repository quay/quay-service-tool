### --- Frontend build --- ###

FROM registry.redhat.io/ubi9/nodejs-22@sha256:6d86fecb222cfc477376a582665e55741cf403240a83bee2b59331c77a4dce96 AS frontend-base

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

FROM registry.access.redhat.com/ubi9/python-312:latest@sha256:608649675c344ac80d58842b883515f39a2232398386805bc6a741f823340a4e AS backend-base

ENV SERVICETOOLDIR=/backend

COPY --from=ghcr.io/astral-sh/uv:0.12.15@sha256:62f8c047d0a0e9ece6b53fc63df902585a67a47a7f318ddec4a37db586edc8e3 /uv /bin/uv

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
