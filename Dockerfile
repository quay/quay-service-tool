### --- Frontend build --- ###

FROM registry.redhat.io/ubi9/nodejs-22@sha256:4d1828d6fd30e367517d654062d41f41c69b7f751962f963d33dba59c1b630f6 AS frontend-base

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

FROM registry.access.redhat.com/ubi9/python-312:latest@sha256:1628f816cfbb9f1d9bf6faa70e99dd69371d3a30be7bdc047f66a45e1d3dd244 AS backend-base

ENV SERVICETOOLDIR=/backend

COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /bin/uv

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

ENV SERVICETOOL_RUN=/conf \
    SERVICETOOL_LOGGING=syslog

COPY --chown=1001:0 ./conf /conf
COPY --from=frontend-build --chown=1001:0 /frontend/dist /backend/static

RUN chmod -R ug+rwx $SERVICETOOL_RUN

EXPOSE 5000

ENTRYPOINT ["dumb-init", "--", "/conf/entrypoint.sh"]
