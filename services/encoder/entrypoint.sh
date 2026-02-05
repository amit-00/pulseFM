#!/bin/bash

# Run the application
cd /app/services/encoder
uvicorn pulsefm_encoder.main:app --host 0.0.0.0 --port ${PORT:-8080}
