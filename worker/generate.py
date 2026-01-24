import uuid
import os
import logging
from pathlib import Path
from typing import Annotated
from contextlib import asynccontextmanager
import asyncio
import tempfile

from fastapi import FastAPI, HTTPException, Response
from google.cloud.storage import Bucket
from pydantic import BaseModel, AfterValidator
from google.cloud import firestore
from google.cloud import storage
from dotenv import load_dotenv
from pydub import AudioSegment

from encoder import encode_stream, OutputFormat

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


BUCKET_NAME = os.getenv("STORAGE_BUCKET")
STUBS_FOLDER = "stubbed"


def init_bucket() -> Bucket:
    logger.info(f"Initializing GCS bucket: {BUCKET_NAME}")
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        logger.info(f"Successfully initialized bucket: {BUCKET_NAME}")
        return bucket
    except Exception as e:
        logger.error(f"Failed to initialize bucket {BUCKET_NAME}: {e}", exc_info=True)
        raise


def _upload_to_gcs(bucket: Bucket, local_path: Path, object_name: str, content_type: str = "audio/wav") -> str:
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
    try:
        return await asyncio.to_thread(_upload_to_gcs, bucket, local_path, object_name, content_type)
    except Exception as e:
        logger.error(f"Error in async upload to GCS: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _download_from_gcs(bucket: Bucket, object_name: str, local_path: Path) -> Path:
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
    try:
        return await asyncio.to_thread(_download_from_gcs, bucket, object_name, local_path)
    except Exception as e:
        logger.error(f"Error in async download from GCS: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def fail_request(request_ref: firestore.DocumentReference, error: str):
    logger.error(f"Failing request {request_ref.id}: {error}")
    try:
        await request_ref.set({
            "status": "failed"
        }, merge=True)
        logger.info(f"Updated request {request_ref.id} status to 'failed'")
    except Exception as e:
        logger.error(f"Failed to update request status in Firestore: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=error)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application lifespan")
    try:
        bucket: Bucket = init_bucket()
        app.state.bucket = bucket

        logger.info("Initializing Firestore client")
        db: firestore.AsyncClient = firestore.AsyncClient()
        app.state.db = db
        logger.info("Application startup complete")

        yield
    except Exception as e:
        logger.error(f"Error during application startup: {e}", exc_info=True)
        raise
    finally:
        logger.info("Application shutdown")


app = FastAPI(lifespan=lifespan)


class GenerateRequest(BaseModel):
    request_id: Annotated[
        str, 
        AfterValidator(lambda x: str(uuid.UUID(x)))
    ]


async def encode_file_to_m4a(
    input_path: Path,
    output_path: Path
) -> Path:
    """
    Encode an audio file to .m4a format with Opus codec.
    Uses temp files for robust processing.
    """
    logger.info(f"Encoding {input_path} to {output_path}")
    
    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Collect encoded chunks from encoder
        chunks = []
        async for chunk in encode_stream(
            file_url=str(input_path),
            output_format=OutputFormat.M4A,
            bitrate=128000,
            sample_rate=48000,
            channels=2
        ):
            chunks.append(chunk)
        
        # Write encoded chunks to output file
        def write_file():
            with open(output_path, 'wb') as f:
                f.write(b''.join(chunks))
        
        await asyncio.to_thread(write_file)
        
        logger.info(f"Successfully encoded file to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to encode file to .m4a: {e}", exc_info=True)
        # Clean up output file on error
        if output_path.exists():
            try:
                os.remove(output_path)
                logger.debug(f"Cleaned up output file after error: {output_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up output file {output_path}: {cleanup_error}")
        raise


async def get_duration_ms(file_path: Path) -> int:
    audio = AudioSegment.from_file(file_path)
    return len(audio)

async def download_encode_and_upload(
    bucket: Bucket,
    source_object_name: str,
    dest_object_name: str
) -> str:
    """
    Download asset from GCS, encode to .m4a with Opus codec, and upload to GCS.
    Uses temp files with robust cleanup.
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




@app.post("/generate")
async def generate(payload: GenerateRequest):
    request_id = payload.request_id
    logger.info(f"Received generate request for request_id: {request_id}")
    
    db: firestore.AsyncClient = app.state.db
    bucket: Bucket = app.state.bucket

    request_ref = db.collection("requests").document(request_id)
    logger.debug(f"Fetching request document: {request_id}")
    request = await request_ref.get()
    
    if not request.exists:
        logger.warning(f"Request not found: {request_id}")
        raise HTTPException(status_code=404, detail="Request not found")

    logger.info(f"Updating request {request_id} status to 'generating'")
    await request_ref.set({
        "status": "generating"
    }, merge=True)

    audio_url = None

    try:
        request_data = request.to_dict()
        logger.debug(f"Request data: {request_data}")
        
        # Download asset, encode to .m4a, and upload to GCS
        # Uses temp files with automatic cleanup
        source_object_name = f"{STUBS_FOLDER}/{request_data['energy']}.wav"
        audio_url, duration_ms = await download_encode_and_upload(
            bucket,
            source_object_name,
            f"{request_id}.m4a"
        )
            
    except Exception as e:
        logger.error(f"Error processing request {request_id}: {e}", exc_info=True)
        await fail_request(request_ref, str(e))

    if audio_url is None:
        logger.error(f"Output URL is None for request {request_id}")
        await fail_request(request_ref, "Failed to generate music")

    # Succesful generation
    try:
        await request_ref.set({
            "status": "ready",
            "audio_url": audio_url,
            "duration_ms": duration_ms
        }, merge=True)
    except Exception as e:
        logger.error(f"Failed to update request status in Firestore: {e}", exc_info=True)
        await fail_request(request_ref, "Failed to update request status in Firestore")

    logger.info(f"Successfully completed generate request for {request_id}")
    return Response(status_code=204)


@app.post("/generate-stubbed")
async def generate(payload: GenerateRequest):
    request_id = payload.request_id
    logger.info(f"Received generate request for request_id: {request_id}")
    
    db: firestore.AsyncClient = app.state.db
    bucket: Bucket = app.state.bucket

    request_ref = db.collection("requests").document(request_id)
    logger.debug(f"Fetching request document: {request_id}")
    request = await request_ref.get()
    
    if not request.exists:
        logger.warning(f"Request not found: {request_id}")
        raise HTTPException(status_code=404, detail="Request not found")

    audio_url = None

    try:
        request_data = request.to_dict()
        
        # Download asset, encode to .m4a, and upload to GCS
        # Uses temp files with automatic cleanup
        source_object_name = f"{STUBS_FOLDER}/{request_data['energy']}.wav"
        audio_url, duration_ms = await download_encode_and_upload(
            bucket,
            source_object_name,
            f"{request_id}.m4a"
        )
            
    except Exception as e:
        logger.error(f"Error processing request {request_id}: {e}", exc_info=True)
        await fail_request(request_ref, str(e))

    if audio_url is None:
        logger.error(f"Output URL is None for request {request_id}")
        await fail_request(request_ref, "Failed to generate music")

    stub_ref = db.collection("stubbed").document(request_id)
    stub_data = {
        **request_data,
        "audio_url": audio_url,
        "duration_ms": duration_ms,
        "status": "ready"
    }

    # Succesful generation
    try:    
        await stub_ref.set(stub_data, merge=True)
    except Exception as e:
        logger.error(f"Failed to update request status in Firestore: {e}", exc_info=True)
        await fail_request(request_ref, "Failed to update request status in Firestore")

    logger.info(f"Successfully completed generate request for {request_id}")
    return Response(status_code=204)