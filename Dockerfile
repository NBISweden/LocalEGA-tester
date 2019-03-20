FROM python:3.6-alpine3.8

LABEL maintainer "EGA System Developers"
LABEL org.label-schema.schema-version="1.0"

ADD requirements.txt .

RUN apk add --no-cache git postgresql-libs postgresql-dev gcc musl-dev libffi-dev make gnupg && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip && \
    apk del --no-cache --purge git postgresql-dev gcc musl-dev libffi-dev make && \
    rm -rf /var/cache/apk/*

ADD test.py .

ADD entrypoint.sh .

VOLUME /conf

ENTRYPOINT [ "/bin/sh", "entrypoint.sh" ]
