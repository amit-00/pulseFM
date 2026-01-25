import logging
from typing import Tuple
from google.cloud import storage

logger = logging.getLogger(__name__)


def parse_gcs_path(blob_path: str) -> Tuple[str, str]:
    if not blob_path.startswith("gs://"):
        raise ValueError(f"Invalid GCS path format: {blob_path}. Must start with 'gs://'")
    
    # Remove gs:// prefix
    path_without_prefix = blob_path[5:]
    
    # Split into bucket and blob name
    parts = path_without_prefix.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GCS path format: {blob_path}. Expected gs://bucket/path")
    
    bucket_name, blob_name = parts
    if not bucket_name:
        raise ValueError(f"Invalid GCS path: bucket name is empty in {blob_path}")
    if not blob_name:
        raise ValueError(f"Invalid GCS path: blob name is empty in {blob_path}")
    
    return bucket_name, blob_name


def get_storage_blob(blob_path: str) -> storage.Blob:
    bucket_name, blob_name = parse_gcs_path(blob_path)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    return bucket.blob(blob_name)