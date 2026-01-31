#!/bin/bash

# Set environment variables
export PROJECT_ID=$PROJECT_ID
export LOCATION=$LOCATION
export MODAL_TOKEN_ID=$MODAL_TOKEN_ID
export MODAL_TOKEN_SECRET=$MODAL_TOKEN_SECRET

# Run the application
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}