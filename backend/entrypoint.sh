#!/bin/bash

# Set environment variables
export PROJECT_ID=$PROJECT_ID
export LOCATION=$LOCATION
export QUEUE_NAME=$QUEUE_NAME
export GEN_WORKER_URL=$GEN_WORKER_URL
export INVOKER_SA_EMAIL=$INVOKER_SA_EMAIL

# Run the application
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}