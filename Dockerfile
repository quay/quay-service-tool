FROM registry.redhat.io/rhel8/nodejs-16 as nodebuild

ENV APP_ROOT=/frontend \
    HOME=/frontend \
    NPM_RUN=start \
    PLATFORM="el8" \
    NODEJS_VERSION=16 \
    NPM_RUN=start \
    NAME=nodejs

COPY --chown=1001:0 ./frontend /frontend

RUN chmod -R ug+rwx /frontend
WORKDIR "$HOME"
USER 1001

RUN npm install --legacy-peer-deps

RUN npm run build


FROM registry.access.redhat.com/ubi8/ubi-minimal:latest AS base

ENV SERVICETOOLDIR=/backend \
    SERVICETOOL_RUN=/conf

COPY --chown=1001:0 ./backend /backend
COPY --chown=1001:0 ./conf /conf
COPY --from=nodebuild --chown=1001:0 /frontend/dist /backend/static

RUN chmod -R ug+rwx $SERVICETOOL_RUN
RUN chmod -R ug+rwx $SERVICETOOLDIR

ENV TZ UTC
RUN set -ex\
	; microdnf -y module enable python39:3.9 \
	; microdnf update -y \
	; microdnf -y --setopt=tsflags=nodocs install \
	python39 \
	gcc-c++ \
	git \
	openldap-devel \
	python39-devel \
	libffi-devel \
        openssl-devel \
        diffutils \
        file \
        make \
        libjpeg-turbo \
	libjpeg-turbo-devel \python3-gpg git python39-devel gcc-c++ libffi-devel \
	; microdnf -y clean all && rm -rf /var/cache/yum


WORKDIR "$SERVICETOOLDIR"
RUN python3 -m pip install --no-cache-dir --upgrade setuptools pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt --no-cache && \
    python3 -m pip freeze

EXPOSE 5000
USER 1001

ENTRYPOINT ["dumb-init", "--", "/conf/entrypoint.sh"]
