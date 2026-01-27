# Use NVIDIA CUDA base image with Python for GPU support
# Compatible with Cloud Run GPU (L4)
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Set working directory
WORKDIR /app

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11, ffmpeg, git, and other dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    git \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python

# Upgrade pip
RUN python3 -m pip install --upgrade pip

# Set environment variables for HuggingFace and model caching
ENV HF_HOME=/app/hf_cache
ENV HF_HUB_ENABLE_HF_TRANSFER=1
ENV TORCH_HOME=/app/torch_cache
ENV ACE_STEP_CHECKPOINT_PATH=/app/checkpoints

# Create cache directories
RUN mkdir -p $HF_HOME $TORCH_HOME /app/checkpoints

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
# Install torch with CUDA support first for proper GPU detection
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install remaining dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install ACE-Step from GitHub
RUN git clone https://github.com/ace-step/ACE-Step.git /tmp/ace-step && \
    cd /tmp/ace-step && \
    pip install --no-cache-dir -e . && \
    rm -rf /tmp/ace-step/.git

# Copy application code
COPY app/ app/

# Copy entrypoint script
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8080

# Run the application using exec form for proper signal handling
# Cloud Run sets PORT environment variable, default to 8080 if not set
ENTRYPOINT ["./entrypoint.sh"]
