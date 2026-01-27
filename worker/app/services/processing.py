"""Audio processing service."""
import logging
import os
import tempfile
import asyncio
from pathlib import Path

from google.cloud.storage import Bucket

from app.services.storage import download_file_from_gcs, upload_file_to_gcs
from app.services.encoding import encode_file_to_m4a, get_duration_ms

logger = logging.getLogger(__name__)


async def download_encode_and_upload(
    bucket: Bucket,
    source_object_name: str,
    dest_object_name: str
) -> tuple[str, int]:
    """
    Download asset from GCS, encode to .m4a with Opus codec, and upload to GCS.
    Uses temp files with robust cleanup.
    
    Returns:
        tuple[str, int]: (gs_url, duration_ms)
    """
    logger.info(f"Processing {source_object_name} -> encode -> {dest_object_name}")
    
    # Initialize paths to None for cleanup safety
    source_path: Path | None = None
    encoded_path: Path | None = None
    
    try:
        # Create temp file for source WAV
        source_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        source_path = Path(source_temp.name)
        source_temp.close()
        
        # Create temp file for encoded M4A
        encoded_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.m4a')
        encoded_path = Path(encoded_temp.name)
        encoded_temp.close()
        
        logger.debug(f"Created temp files: source={source_path}, encoded={encoded_path}")
        
        # Step 1: Download source file from GCS
        logger.debug(f"Downloading {source_object_name} from GCS")
        await download_file_from_gcs(bucket, source_object_name, source_path)
        logger.debug(f"Downloaded {source_object_name} to {source_path}")
        
        # Step 2: Encode to M4A
        logger.debug(f"Encoding {source_path} to {encoded_path}")
        await encode_file_to_m4a(source_path, encoded_path)
        logger.debug(f"Encoded to {encoded_path}")

        duration_ms = await asyncio.to_thread(get_duration_ms, encoded_path)
        
        # Step 3: Upload encoded file to GCS
        logger.debug(f"Uploading {encoded_path} to GCS as {dest_object_name}")
        gs_url = await upload_file_to_gcs(
            bucket,
            encoded_path,
            dest_object_name,
            content_type="audio/mp4"
        )
        logger.info(f"Successfully processed and uploaded: {gs_url}")
        
        return gs_url, duration_ms
        
    except Exception as e:
        logger.error(f"Failed to download, encode, and upload: {e}", exc_info=True)
        raise
        
    finally:
        # Clean up temp files - always execute, even on errors
        cleanup_errors = []
        
        # Clean up source temp file
        if source_path is not None and source_path.exists():
            try:
                os.remove(source_path)
                logger.debug(f"Cleaned up source temp file: {source_path}")
            except Exception as e:
                cleanup_error = f"Failed to remove {source_path}: {e}"
                cleanup_errors.append(cleanup_error)
                logger.warning(cleanup_error)
        
        # Clean up encoded temp file
        if encoded_path is not None and encoded_path.exists():
            try:
                os.remove(encoded_path)
                logger.debug(f"Cleaned up encoded temp file: {encoded_path}")
            except Exception as e:
                cleanup_error = f"Failed to remove {encoded_path}: {e}"
                cleanup_errors.append(cleanup_error)
                logger.warning(cleanup_error)
        
        # Log summary if any cleanup errors occurred (non-fatal)
        if cleanup_errors:
            logger.warning(f"Some temp files could not be cleaned up (non-fatal): {len(cleanup_errors)} errors")

