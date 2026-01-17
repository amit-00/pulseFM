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
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security and make entrypoint executable
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod +x /app/entrypoint.sh
USER appuser

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8080

# Run the application
# Cloud Run sets PORT env var, default to 8080 if not set
CMD ["/app/entrypoint.sh"]

