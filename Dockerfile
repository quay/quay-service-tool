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

RUN npm install

RUN npm run build

FROM registry.redhat.io/rhel8/python-38

ENV SERVICETOOLDIR=/service-tool \
    SERVICETOOL_PYTHONPATH=/service-tool/backend \
    SERVICETOOL_RUN=/service-tool/conf

RUN mkdir $SERVICETOOLDIR
WORKDIR $SERVICETOOLDIR

COPY backend /backend
COPY --chown=1001:0 conf /conf
COPY --from=nodebuild /frontend/dist /backend/static

RUN chmod -R ug+rwx $SERVICETOOLDIR

RUN python -m pip install --no-cache-dir --upgrade setuptools pip && \
    python -m pip install --no-cache-dir -r requirements.txt --no-cache && \
    python -m pip freeze

EXPOSE 5000
USER 1001

ENTRYPOINT ["dumb-init", "--", "/service-tool/conf/entrypoint.sh"]
