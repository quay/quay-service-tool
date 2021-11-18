FROM quay.io/bitnami/node:17 as nodebuild

COPY ./frontend /frontend

WORKDIR /frontend

RUN npm install

RUN npm run build

FROM quay.io/centos/centos:8

COPY backend /backend

#RUN chmod 777 -R /backend
#RUN chown $USER:$GROUP -R /backend
WORKDIR /backend

COPY --from=nodebuild /frontend/dist /backend/static

RUN yum update -y
RUN yum groupinstall "Development Tools" -y && \
    yum install openssl-devel libffi-devel bzip2-devel -y
RUN yum install wget -y
RUN wget https://www.python.org/ftp/python/3.9.0/Python-3.9.0.tgz
RUN tar xvf Python-3.9.0.tgz

RUN cd Python-3.9*/ && ./configure --enable-optimizations && make install

RUN ln -fs /usr/local/bin/python3.9 /usr/bin/python


RUN python -m pip install --no-cache-dir --upgrade setuptools pip && \
    python -m pip install --no-cache-dir -r requirements.txt --no-cache && \
    python -m pip freeze


EXPOSE 5000

ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0:5000", "app:app"]
