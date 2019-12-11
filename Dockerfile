FROM python:3.6-alpine3.10 as BUILD

RUN apk add --no-cache git postgresql-libs postgresql-dev gcc musl-dev libffi-dev make gnupg && \
    rm -rf /var/cache/apk/*

COPY requirements.txt /root/legatester/requirements.txt
COPY lega_tester /root/legatester/lega_tester
COPY setup.py /root/legatester

RUN pip install --upgrade pip && \
    pip install -r /root/legatester/requirements.txt && \
    pip install /root/legatester

FROM python:3.6-alpine3.10

LABEL maintainer "NeIC System Developers"
LABEL org.label-schema.schema-version="1.0"

RUN apk add --no-cache --update libressl postgresql-libs openssh-client curl

RUN addgroup -g 1000 lega && \
    adduser -D -u 1000 -G lega lega

RUN mkdir /volume && \
    chmod 777 /volume

VOLUME /volume

COPY --from=BUILD /usr/local/lib/python3.6/ usr/local/lib/python3.6/

COPY --from=BUILD /usr/local/bin/legatest /usr/local/bin/

COPY --from=BUILD /usr/local/bin/legaenc /usr/local/bin/

ADD entrypoint.sh .

VOLUME /conf

ENTRYPOINT [ "/bin/sh", "entrypoint.sh" ]
