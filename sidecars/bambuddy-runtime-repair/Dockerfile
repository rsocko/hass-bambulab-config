FROM python:3.13-slim

WORKDIR /app

COPY sidecars/bambuddy-runtime-repair/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY tools /app/tools
COPY sidecars/bambuddy-runtime-repair/app /app/app

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]