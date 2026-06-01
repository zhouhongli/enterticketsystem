FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends tini && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir setuptools

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir .

COPY backend/app/ ./app/
COPY backend/seed.py ./seed.py
COPY frontend/ ./frontend/
COPY start-entrypoint.sh /app/start-entrypoint.sh

RUN mkdir -p /app/data && \
    chmod -R a+rw /app/data && \
    chmod +x /app/start-entrypoint.sh

ENV APP_NAME="企业售后工单系统" \
    APP_ENV="production" \
    TICKET_DATA_FILE="/app/data/store.json" \
    SESSION_COOKIE_SECURE="true" \
    SESSION_TTL_HOURS="8"

EXPOSE 8000

ENTRYPOINT ["tini", "--", "/app/start-entrypoint.sh"]
