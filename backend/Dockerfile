FROM registry.redhat.io/rhel8/python-39

COPY --chown=0:0 backend /backend

WORKDIR /backend

RUN python -m pip install --no-cache-dir --upgrade setuptools pip && \
    python -m pip install --no-cache-dir -r requirements.txt --no-cache && \
    python -m pip freeze

EXPOSE 5000

ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0:5000", "app:app"]
