import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from pydub import AudioSegment
from google.cloud.storage import Client as StorageClient
from google.cloud.firestore import AsyncClient, SERVER_TIMESTAMP

from pulsefm_encoder.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MAX_BYTES = 100 * 1024 * 1024
EVENT_TYPE_FINALIZED = "google.cloud.storage.object.v1.finalized"


class GcsObject(BaseModel):
    bucket: str
    name: str
    size: str | None = None
    contentType: str | None = None


class CloudEventEnvelope(BaseModel):
    type: str
    data: Dict[str, Any]


_storage: StorageClient | None = None
_db: AsyncClient | None = None


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global _storage, _db
    _storage = StorageClient()
    _db = AsyncClient()
    yield


app = FastAPI(title="PulseFM Encoder", version="1.0.0", lifespan=_lifespan)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _size_ok(size_value: str | None) -> bool:
    if size_value is None:
        return True
    try:
        return int(size_value) <= MAX_BYTES
    except ValueError:
        return True


def _parse_and_filter(request: Request, body: Dict[str, Any]) -> GcsObject | None:
    event_type, data = _parse_cloud_event(request, body)

    if event_type != EVENT_TYPE_FINALIZED:
        logger.info("Ignoring event type: %s", event_type)
        return None

    obj = GcsObject(**data)

    if obj.bucket != settings.raw_bucket:
        logger.info("Ignoring bucket %s", obj.bucket)
        return None
    if not obj.name.startswith(settings.raw_prefix):
        logger.info("Ignoring object outside raw prefix: %s", obj.name)
        return None
    if not obj.name.lower().endswith(".wav"):
        logger.info("Ignoring non-wav file: %s", obj.name)
        return None
    if not _size_ok(obj.size):
        logger.warning("File too large (event size): %s", obj.size)
        return None

    return obj


def _encode_audio_sync(storage: StorageClient, gcs_object: GcsObject) -> tuple[str, int]:
    """Download WAV, encode to AAC, upload. Runs in a worker thread."""
    bucket = storage.bucket(gcs_object.bucket)
    blob = bucket.blob(gcs_object.name)
    blob.reload()

    if blob.size is not None and blob.size > MAX_BYTES:
        logger.warning("File too large (blob size): %s", blob.size)
        return ("", -1)

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

        output_bucket = storage.bucket(settings.encoded_bucket)
        output_blob_name = f"{settings.encoded_prefix}{output_name}"
        output_blob = output_bucket.blob(output_blob_name)
        # Encoded object names are voteId-based and immutable, so cache aggressively.
        output_blob.cache_control = settings.encoded_cache_control
        output_blob.upload_from_filename(str(output_path), content_type="audio/mp4")

    logger.info("Encoded %s to gs://%s/%s", gcs_object.name, settings.encoded_bucket, output_blob_name)
    return (vote_id, duration_ms)


async def _persist_metadata(db: AsyncClient, vote_id: str, duration_ms: int) -> None:
    song_ref = db.collection(settings.songs_collection).document(vote_id)
    await song_ref.set({
        "durationMs": duration_ms,
        "status": "ready",
        "createdAt": SERVER_TIMESTAMP,
    })
    logger.info("Updated songs/%s with durationMs=%s", vote_id, duration_ms)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}


@app.post("/")
async def handle_event(request: Request) -> Dict[str, str]:
    try:
        body = await request.json()
    except ValueError:
        logger.warning("Invalid JSON body")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )

    gcs_object = _parse_and_filter(request, body)
    if gcs_object is None:
        return {"status": "ignored"}

    if _storage is None or _db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service not initialized",
        )

    vote_id, duration_ms = await asyncio.to_thread(_encode_audio_sync, _storage, gcs_object)
    if duration_ms < 0:
        return {"status": "skipped"}

    await _persist_metadata(_db, vote_id, duration_ms)
    return {"status": "ok"}
