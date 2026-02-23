#!/usr/bin/env bash
set -euo pipefail

cd /app/services/modal-dispatch-service
uvicorn pulsefm_modal_dispatch_service.main:app --host 0.0.0.0 --port ${PORT:-8080}
