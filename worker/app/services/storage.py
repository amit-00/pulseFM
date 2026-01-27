"""Google Cloud Storage service."""
import logging
import asyncio
from pathlib import Path

from google.cloud.storage import Bucket, Client
from fastapi import HTTPException

from app.config.settings import BUCKET_NAME

logger = logging.getLogger(__name__)


def init_bucket() -> Bucket:
    """Initialize and return GCS bucket."""
    logger.info(f"Initializing GCS bucket: {BUCKET_NAME}")
    try:
        client = Client()
        bucket = client.bucket(BUCKET_NAME)
        logger.info(f"Successfully initialized bucket: {BUCKET_NAME}")
        return bucket
    except Exception as e:
        logger.error(f"Failed to initialize bucket {BUCKET_NAME}: {e}", exc_info=True)
        raise


def _upload_to_gcs(bucket: Bucket, local_path: Path, object_name: str, content_type: str = "audio/wav") -> str:
    """Upload file to GCS (synchronous)."""
    logger.info(f"Uploading file to GCS: {local_path} -> {object_name}")
    try:
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(local_path), content_type=content_type)
        gs_url = f"gs://{BUCKET_NAME}/{object_name}"
        logger.info(f"Successfully uploaded file to GCS: {gs_url}")
        return gs_url
    except Exception as e:
        logger.error(f"Failed to upload file to GCS: {e}", exc_info=True)
        raise


async def upload_file_to_gcs(bucket: Bucket, local_path: Path, object_name: str, content_type: str = "audio/wav") -> str:
    """Upload file to GCS (asynchronous)."""
    try:
        return await asyncio.to_thread(_upload_to_gcs, bucket, local_path, object_name, content_type)
    except Exception as e:
        logger.error(f"Error in async upload to GCS: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _download_from_gcs(bucket: Bucket, object_name: str, local_path: Path) -> Path:
    """Download file from GCS (synchronous)."""
    logger.info(f"Downloading file from GCS: {object_name} -> {local_path}")
    try:
        blob = bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(f"File not found in GCS: {object_name}")
        blob.download_to_filename(str(local_path))
        logger.info(f"Successfully downloaded file from GCS: {object_name}")
        return local_path
    except Exception as e:
        logger.error(f"Failed to download file from GCS: {e}", exc_info=True)
        raise


async def download_file_from_gcs(bucket: Bucket, object_name: str, local_path: Path) -> Path:
    """Download file from GCS (asynchronous)."""
    try:
        return await asyncio.to_thread(_download_from_gcs, bucket, object_name, local_path)
    except Exception as e:
        logger.error(f"Error in async download from GCS: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

