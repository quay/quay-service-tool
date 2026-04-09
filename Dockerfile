FROM registry.redhat.io/ubi9/nodejs-22@sha256:052f576671bd8f7f8276b84a3eaef08e3e1de4d669270e8f2543bf23d3e168a4 AS nodebuild

ENV APP_ROOT=/frontend \
    HOME=/frontend \
    NPM_RUN=start \
    PLATFORM="el8" \
    NODEJS_VERSION=22 \
    NPM_RUN=start \
    NAME=nodejs

COPY --chown=1001:0 ./frontend /frontend

RUN chmod -R ug+rwx /frontend
WORKDIR "$HOME"
USER 1001

RUN npm install --legacy-peer-deps

RUN npm run build


FROM registry.access.redhat.com/ubi9/python-312:latest@sha256:5e80833fe6cca33826db27373f1cd119bcc32e9daa26afd6cca7aeae289cf156 AS base

ENV SERVICETOOLDIR=/backend \
    SERVICETOOL_RUN=/conf \
    SERVICETOOL_LOGGING=syslog

COPY --from=ghcr.io/astral-sh/uv:0.11.3@sha256:90bbb3c16635e9627f49eec6539f956d70746c409209041800a0280b93152823 /uv /bin/uv

COPY --chown=1001:0 ./backend /backend
COPY --chown=1001:0 ./conf /conf
COPY --from=nodebuild --chown=1001:0 /frontend/dist /backend/static

RUN chmod -R ug+rwx $SERVICETOOL_RUN
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

EXPOSE 5000

ENTRYPOINT ["dumb-init", "--", "/conf/entrypoint.sh"]
