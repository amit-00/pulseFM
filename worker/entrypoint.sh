#!/bin/sh
exec uvicorn generate:app --host 0.0.0.0 --port ${PORT:-8080}

