import uuid
import shutil
import os
import logging
from pathlib import Path
from datetime import datetime
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

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


BUCKET_NAME = os.getenv("STORAGE_BUCKET")
ASSET_PATH = Path("/app/assets")
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


def _upload_to_gcs(bucket: Bucket, local_path: Path, object_name: str) -> str:
    logger.info(f"Uploading file to GCS: {local_path} -> {object_name}")
    try:
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(local_path), content_type="audio/wav")
        gs_url = f"gs://{BUCKET_NAME}/{object_name}"
        logger.info(f"Successfully uploaded file to GCS: {gs_url}")
        return gs_url
    except Exception as e:
        logger.error(f"Failed to upload file to GCS: {e}", exc_info=True)
        raise


async def upload_file_to_gcs(bucket: Bucket, local_path: Path, object_name: str) -> str:
    try:
        return await asyncio.to_thread(_upload_to_gcs, bucket, local_path, object_name)
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


async def select_asset(bucket: Bucket, energy: str) -> Path:
    """Download asset file from GCS bucket /stubs folder"""
    object_name = f"{STUBS_FOLDER}/{energy}.wav"
    logger.debug(f"Downloading asset for energy '{energy}' from GCS: {object_name}")
    
    # Create a temporary file to store the downloaded asset
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_path = Path(temp_file.name)
    temp_file.close()
    
    try:
        await download_file_from_gcs(bucket, object_name, temp_path)
        logger.debug(f"Successfully downloaded asset: {temp_path}")
        return temp_path
    except Exception as e:
        # Clean up temp file on error
        if temp_path.exists():
            os.remove(temp_path)
        raise


async def generate_music(bucket: Bucket, request: dict):
    request_id = request['request_id']
    energy = request["energy"]
    logger.info(f"Generating music for request {request_id} with energy '{energy}'")
    
    output_path = ASSET_PATH / f"{request_id}.wav"
    asset = await select_asset(bucket, energy)
    
    try:
        logger.debug(f"Copying asset from {asset} to {output_path}")
        shutil.copy(asset, output_path)
        logger.info(f"Successfully generated music file: {output_path}")
        return output_path
    finally:
        # Clean up downloaded asset file
        if asset.exists():
            try:
                os.remove(asset)
                logger.debug(f"Cleaned up downloaded asset file: {asset}")
            except Exception as e:
                logger.warning(f"Failed to clean up asset file {asset}: {e}")


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

    output_url = None

    try:
        request_data = request.to_dict()
        logger.debug(f"Request data: {request_data}")
        
        wav_path = await generate_music(bucket, request_data)
        output_url = await upload_file_to_gcs(bucket, wav_path, f"{request_id}.wav")

        logger.info(f"Updating request {request_id} status to 'completed' with output_url: {output_url}")
        await request_ref.set({
            "status": "completed",
            "output_url": output_url
        }, merge=True)
        
        # Clean up local file after successful upload
        try:
            if wav_path.exists():
                os.remove(wav_path)
                logger.debug(f"Cleaned up local file: {wav_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up local file {wav_path}: {e}")
            
    except Exception as e:
        logger.error(f"Error processing request {request_id}: {e}", exc_info=True)
        await fail_request(request_ref, str(e))

    if output_url is None:
        logger.error(f"Output URL is None for request {request_id}")
        await fail_request(request_ref, "Failed to generate music")

    # Succesful generation
    try:
        await request_ref.set({
            "status": "ready",
            "output_url": output_url
        }, merge=True)
    except Exception as e:
        logger.error(f"Failed to update request status in Firestore: {e}", exc_info=True)
        await fail_request(request_ref, "Failed to update request status in Firestore")

    logger.info(f"Successfully completed generate request for {request_id}")
    return Response(status_code=204)