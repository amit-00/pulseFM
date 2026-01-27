"""Application configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = os.getenv("STORAGE_BUCKET")
STUBS_FOLDER = "stubbed"

