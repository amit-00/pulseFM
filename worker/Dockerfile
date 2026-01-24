# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY generate.py .

# Copy encoder code
COPY encoder.py .

# Copy assets
COPY assets/ assets/

# Copy entrypoint script
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8080

# Run the application using exec form for proper signal handling
# Cloud Run sets PORT environment variable, default to 8080 if not set
ENTRYPOINT ["./entrypoint.sh"]

