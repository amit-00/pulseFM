#!/bin/bash

cd /app/services/vote-api
uvicorn pulsefm_vote_api.main:app --host 0.0.0.0 --port ${PORT:-8080}
