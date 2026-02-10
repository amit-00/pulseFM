import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from pydub import AudioSegment
from google.cloud.storage import Client as StorageClient
from google.cloud.firestore import AsyncClient, SERVER_TIMESTAMP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

MAX_BYTES = 100 * 1024 * 1024
EVENT_TYPE_FINALIZED = "google.cloud.storage.object.v1.finalized"

RAW_BUCKET = os.getenv("RAW_BUCKET", "pulsefm-generated-songs")
RAW_PREFIX = os.getenv("RAW_PREFIX", "raw/")
ENCODED_BUCKET = os.getenv("ENCODED_BUCKET", RAW_BUCKET)
ENCODED_PREFIX = os.getenv("ENCODED_PREFIX", "encoded/")
SONGS_COLLECTION = os.getenv("SONGS_COLLECTION", "songs")


class GcsObject(BaseModel):
    bucket: str
    name: str
    size: Optional[str] = None
    contentType: Optional[str] = None


class CloudEventEnvelope(BaseModel):
    type: str
    data: Dict[str, Any]


app = FastAPI(title="PulseFM Encoder", version="1.0.0")


def _normalize_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    return prefix if prefix.endswith("/") else f"{prefix}/"


def _parse_cloud_event(request: Request, body: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    ce_type = request.headers.get("ce-type")
    if ce_type:
        return ce_type, body

    if "type" in body and "data" in body:
        envelope = CloudEventEnvelope(**body)
        return envelope.type, envelope.data

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Missing CloudEvent headers or structured envelope",
    )


def _size_ok(size_value: Optional[str]) -> bool:
    if size_value is None:
        return True
    try:
        return int(size_value) <= MAX_BYTES
    except ValueError:
        return True


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}


@app.post("/")
async def handle_event(request: Request) -> Dict[str, str]:
    try:
        body = await request.json()
    except Exception:
        logger.warning("Invalid JSON body")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )
    event_type, data = _parse_cloud_event(request, body)

    if event_type != EVENT_TYPE_FINALIZED:
        logger.info("Ignoring event type: %s", event_type)
        return {"status": "ignored"}

    gcs_object = GcsObject(**data)
    raw_prefix = _normalize_prefix(RAW_PREFIX)
    encoded_prefix = _normalize_prefix(ENCODED_PREFIX)

    if gcs_object.bucket != RAW_BUCKET:
        logger.info("Ignoring bucket %s", gcs_object.bucket)
        return {"status": "ignored"}

    if not gcs_object.name.startswith(raw_prefix):
        logger.info("Ignoring object outside raw prefix: %s", gcs_object.name)
        return {"status": "ignored"}

    if not gcs_object.name.lower().endswith(".wav"):
        logger.info("Ignoring non-wav file: %s", gcs_object.name)
        return {"status": "ignored"}

    if not _size_ok(gcs_object.size):
        logger.warning("File too large (event size): %s", gcs_object.size)
        return {"status": "skipped"}

    storage_client = StorageClient()
    bucket = storage_client.bucket(gcs_object.bucket)
    blob = bucket.blob(gcs_object.name)
    blob.reload()

    if blob.size is not None and blob.size > MAX_BYTES:
        logger.warning("File too large (blob size): %s", blob.size)
        return {"status": "skipped"}

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / Path(gcs_object.name).name
        vote_id = Path(gcs_object.name).stem
        output_name = f"{vote_id}.m4a"
        output_path = Path(tmpdir) / output_name

        blob.download_to_filename(str(input_path))

        audio = AudioSegment.from_wav(str(input_path))
        duration_ms = len(audio)
        audio.export(
            str(output_path),
            format="ipod",
            codec="aac",
            bitrate="128k",
            parameters=["-ar", "48000"],
        )

        output_bucket = storage_client.bucket(ENCODED_BUCKET)
        output_blob_name = f"{encoded_prefix}{output_name}"
        output_blob = output_bucket.blob(output_blob_name)
        output_blob.upload_from_filename(
            str(output_path),
            content_type="audio/mp4",
        )

        logger.info(
            "Encoded %s to gs://%s/%s",
            gcs_object.name,
            ENCODED_BUCKET,
            output_blob_name,
        )

    try:
        db = AsyncClient()
        song_ref = db.collection(SONGS_COLLECTION).document(vote_id)
        await song_ref.set({
            "durationMs": duration_ms,
            "status": "ready",
            "createdAt": SERVER_TIMESTAMP,
        })
        logger.info("Updated songs/%s with durationMs=%s", vote_id, duration_ms)
    except Exception as exc:
        logger.exception("Failed to update songs/%s: %s", vote_id, exc)

    return {"status": "ok"}
