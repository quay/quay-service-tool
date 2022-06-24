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

ENV SERVICETOOLDIR /backend
ENV SERVICETOOL_RUN=/backend/conf

COPY backend /backend
COPY conf /backend/conf
RUN chmod -R 777 /backend/conf

COPY --from=nodebuild /frontend/dist /backend/static

WORKDIR /backend

RUN python -m pip install --no-cache-dir --upgrade setuptools pip && \
    python -m pip install --no-cache-dir -r requirements.txt --no-cache && \
    python -m pip freeze

EXPOSE 5000

ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0:5000", "app:app"]
