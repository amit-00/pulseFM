#!/bin/bash

# Run the application
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
