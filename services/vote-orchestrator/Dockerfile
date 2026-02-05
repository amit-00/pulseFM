FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY packages/pulsefm-redis packages/pulsefm-redis
COPY packages/pulsefm-firestore packages/pulsefm-firestore
COPY packages/pulsefm-pubsub packages/pulsefm-pubsub
COPY packages/pulsefm-descriptors packages/pulsefm-descriptors
COPY services/vote-orchestrator services/vote-orchestrator

RUN pip install --no-cache-dir \
    ./packages/pulsefm-redis \
    ./packages/pulsefm-firestore \
    ./packages/pulsefm-pubsub \
    ./packages/pulsefm-descriptors \
    ./services/vote-orchestrator

RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/credentials && \
    chown -R appuser:appuser /app && \
    chmod +x /app/services/vote-orchestrator/entrypoint.sh
USER appuser

EXPOSE 8080

CMD ["/app/services/vote-orchestrator/entrypoint.sh"]
