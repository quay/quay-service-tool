FROM registry.redhat.io/ubi9/nodejs-22@sha256:1fe6a3926ed6249559bb079d523a81e4dad1628205edfd9dea9ab8247f08caec AS nodebuild

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


FROM registry.access.redhat.com/ubi9/python-312:latest@sha256:3620b36bfc90e0692f7407ab9b862b6788343d5b059f79f0a9f49edbe09ae68b AS base

ENV SERVICETOOLDIR=/backend \
    SERVICETOOL_RUN=/conf \
    SERVICETOOL_LOGGING=syslog

COPY --from=ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 /uv /bin/uv

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
