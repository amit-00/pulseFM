#!/usr/bin/env bash
set -euo pipefail

cd /app/services/vote-stream
uvicorn pulsefm_vote_stream.main:app --host 0.0.0.0 --port ${PORT:-8080}
