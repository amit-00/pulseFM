#!/usr/bin/env bash
set -euo pipefail

cd /app/services/playback-stream
uvicorn pulsefm_playback_stream.main:app --host 0.0.0.0 --port ${PORT:-8080}
