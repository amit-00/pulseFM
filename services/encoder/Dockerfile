# Use Python 3.11 slim image as base
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy service
COPY services/encoder services/encoder

# Install Python dependencies
RUN pip install --no-cache-dir ./services/encoder

# Create credentials directory and non-root user for security
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/credentials && \
    chown -R appuser:appuser /app && \
    chmod +x /app/services/encoder/entrypoint.sh
USER appuser

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8080

# Run the application
CMD ["/app/services/encoder/entrypoint.sh"]
