FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends tini && \
    rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir .

COPY backend/app/ ./app/
COPY frontend/ ./frontend/

RUN mkdir -p /app/data && \
    chmod -R a+rw /app/data

ENV APP_NAME="企业售后工单系统" \
    APP_ENV="production" \
    TICKET_DATA_FILE="/app/data/store.json" \
    SESSION_COOKIE_SECURE="true" \
    SESSION_TTL_HOURS="8"

EXPOSE 8000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
