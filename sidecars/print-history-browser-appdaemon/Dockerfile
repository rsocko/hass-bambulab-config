FROM python:3.13-slim

WORKDIR /conf

COPY sidecars/print-history-browser-appdaemon/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY sidecars/print-history-browser-appdaemon/conf /conf

ENV PYTHONPATH=/conf/apps

CMD ["appdaemon", "-c", "/conf"]
