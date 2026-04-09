FROM registry.access.redhat.com/ubi9/python-312:latest@sha256:1628f816cfbb9f1d9bf6faa70e99dd69371d3a30be7bdc047f66a45e1d3dd244 AS base

ENV SERVICETOOLDIR=/backend

COPY --from=ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 /uv /bin/uv

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
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR "$SERVICETOOLDIR"
RUN uv sync --frozen --no-dev

EXPOSE 5000
USER 1001

ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0:5000", "--limit-request-field_size", "16384", "app:app"]
