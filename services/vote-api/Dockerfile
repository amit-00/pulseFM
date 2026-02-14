FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY packages/pulsefm-tasks packages/pulsefm-tasks
COPY packages/pulsefm-redis packages/pulsefm-redis
COPY services/vote-api services/vote-api

RUN pip install --no-cache-dir \
    ./packages/pulsefm-tasks \
    ./packages/pulsefm-redis \
    ./services/vote-api

RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/credentials && \
    chown -R appuser:appuser /app && \
    chmod +x /app/services/vote-api/entrypoint.sh
USER appuser

EXPOSE 8080

CMD ["/app/services/vote-api/entrypoint.sh"]
