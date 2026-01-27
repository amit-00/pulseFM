"""Application configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

# GCS Configuration
BUCKET_NAME = os.getenv("STORAGE_BUCKET")
STUBS_FOLDER = "stubbed"

# ACE-Step Model Configuration
ACE_STEP_CHECKPOINT_PATH = os.getenv(
    "ACE_STEP_CHECKPOINT_PATH",
    "/app/checkpoints"  # Default path in Docker container
)

# Generation Configuration
GENERATION_DURATION_SEC = int(os.getenv("GENERATION_DURATION_SEC", "90"))
GENERATION_SEED = os.getenv("GENERATION_SEED")  # None by default for random generation
if GENERATION_SEED is not None:
    GENERATION_SEED = int(GENERATION_SEED)

