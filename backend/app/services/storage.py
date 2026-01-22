import logging
from typing import Optional, Tuple
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError

logger = logging.getLogger(__name__)


def parse_gcs_path(blob_path: str) -> Tuple[str, str]:
    """
    Parse a GCS blob path in the format gs://bucket/path/to/file.
    
    Args:
        blob_path: GCS path in format gs://bucket/path
        
    Returns:
        Tuple of (bucket_name, blob_name)
        
    Raises:
        ValueError: If path format is invalid
    """
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


def generate_signed_url(blob_path: str, expiration_seconds: int = 3600) -> str:
    """
    Generate a signed URL for a GCS blob.
    
    Args:
        blob_path: GCS path in format gs://bucket/path/to/file
        expiration_seconds: URL expiration time in seconds (default: 1 hour)
        
    Returns:
        Signed URL string
        
    Raises:
        ValueError: If blob_path format is invalid
        GoogleCloudError: If GCS operation fails
    """
    try:
        bucket_name, blob_name = parse_gcs_path(blob_path)
        
        # Initialize GCS client
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Generate signed URL
        signed_url = blob.generate_signed_url(
            expiration=expiration_seconds,
            method="GET"
        )
        
        logger.debug(f"Generated signed URL for {blob_path} (expires in {expiration_seconds}s)")
        return signed_url
        
    except ValueError as e:
        logger.error(f"Invalid GCS path format: {e}")
        raise
    except GoogleCloudError as e:
        logger.error(f"GCS error generating signed URL for {blob_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating signed URL for {blob_path}: {e}", exc_info=True)
        raise

