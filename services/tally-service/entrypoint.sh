#!/bin/bash

cd /app/services/tally-service
uvicorn pulsefm_tally_service.main:app --host 0.0.0.0 --port ${PORT:-8080}
