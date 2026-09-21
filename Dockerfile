FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py automation.py storage.py crypto_utils.py ./
COPY templates ./templates
COPY static ./static

RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1 PORT=8787

EXPOSE 8787

CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "120", "--bind", "0.0.0.0:8787", "app:app"]
