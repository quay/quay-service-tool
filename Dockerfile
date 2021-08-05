FROM quay.io/bitnami/node:16 as nodebuild

COPY ./frontend /frontend

WORKDIR /frontend

RUN rm -rf node_modules

RUN npm install

RUN npm run build

FROM quay.io/centos/centos:8

COPY backend /backend

COPY --from=nodebuild /frontend/dist /backend/static

WORKDIR /backend

RUN yum -y install python3
RUN alternatives --set python /usr/bin/python3 && \
    python -m pip install --no-cache-dir --upgrade setuptools pip && \
    python -m pip install --no-cache-dir -r requirements.txt --no-cache && \
    python -m pip freeze

EXPOSE 5000

ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0:5000", "app:app"]
