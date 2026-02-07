#!/bin/bash

cd /app/services/playback-orchestrator
uvicorn pulsefm_playback_orchestrator.main:app --host 0.0.0.0 --port ${PORT:-8080}
