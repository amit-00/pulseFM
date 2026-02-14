#!/usr/bin/env bash
set -euo pipefail

cd /app/services/playback-service
uvicorn pulsefm_playback_service.main:app --host 0.0.0.0 --port ${PORT:-8080}
