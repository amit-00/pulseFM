#!/bin/bash

cd /app/services/vote-orchestrator
uvicorn pulsefm_vote_orchestrator.main:app --host 0.0.0.0 --port ${PORT:-8080}
