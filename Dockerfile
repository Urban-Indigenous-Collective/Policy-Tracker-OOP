FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_DEBUG=0
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "--timeout", "600", "--workers", "1", "--threads", "4", "--worker-class", "gthread", "app:app"]
