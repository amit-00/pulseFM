#!/bin/bash

cd /app/services/tally-worker
uvicorn pulsefm_tally_worker.main:app --host 0.0.0.0 --port ${PORT:-8080}
