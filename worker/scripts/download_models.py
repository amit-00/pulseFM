#!/usr/bin/env python3
"""Pre-download ACE-Step models for Docker build."""
from huggingface_hub import snapshot_download
import os

if __name__ == "__main__":
    checkpoint_dir = os.getenv("ACE_STEP_CHECKPOINT_PATH", "/app/checkpoints")
    cache_dir = os.getenv("HF_HOME", "/app/hf_cache")
    
    print(f"Downloading ACE-Step models to {checkpoint_dir}...")
    snapshot_download(
        repo_id="ACE-Step/ACE-Step-v1-3.5B",
        cache_dir=cache_dir,
        local_dir=f"{checkpoint_dir}/ACE-Step/ACE-Step-v1-3.5B"
    )
    print("Models downloaded successfully!")