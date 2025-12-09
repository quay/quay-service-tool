FROM registry.access.redhat.com/ubi9/python-312:latest AS base

ENV SERVICETOOLDIR=/backend

COPY --from=ghcr.io/astral-sh/uv:0.9.6@sha256:4b96ee9429583983fd172c33a02ecac5242d63fb46bc27804748e38c1cc9ad0d /uv /bin/uv

COPY --chown=1001:0 . /backend

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

ENV UV_COMPILE_BYTECODE=true \
    UV_NO_CACHE=true \
    UV_PYTHON=3.12 \
    PATH="/backend/.venv/bin:$PATH"

WORKDIR "$SERVICETOOLDIR"
RUN uv sync --frozen --no-dev

EXPOSE 5000
USER 1001

ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0:5000", "app:app"]
