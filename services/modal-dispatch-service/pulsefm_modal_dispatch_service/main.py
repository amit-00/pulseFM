import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

import modal
from fastapi import FastAPI, HTTPException, status

from pulsefm_descriptors.data import DESCRIPTORS
from pulsefm_pubsub.client import decode_pubsub_json
from pulsefm_redis.client import get_redis_client
from pulsefm_tasks.client import enqueue_json_task_with_delay

from pulsefm_modal_dispatch_service.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Modal Dispatch Service", version="0.1.0")


def _now_epoch_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _close_done_key(vote_id: str) -> str:
    return f"pulsefm:modal:close:{vote_id}:done"


def _close_lock_key(vote_id: str) -> str:
    return f"pulsefm:modal:close:{vote_id}:lock"


def _warmup_url() -> str:
    base = settings.modal_dispatch_service_url.rstrip("/")
    if not base:
        raise ValueError("MODAL_DISPATCH_SERVICE_URL is required")
    return f"{base}/warmup"


def _parse_end_at_ms(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise ValueError("endAt must be epoch milliseconds")


async def _has_active_listeners() -> bool:
    client = get_redis_client()
    active = await client.get(settings.heartbeat_active_key)  # type: ignore[misc]
    return bool(active)


def _get_descriptor(winner_option: str) -> Dict[str, str]:
    descriptor = DESCRIPTORS.get(winner_option)
    if not descriptor:
        raise ValueError(f"Unknown winner option: {winner_option}")
    return descriptor


def _set_modal_min_instances(min_instances: int) -> None:
    function = modal.Function.from_name(settings.modal_app_name, settings.modal_function_name)
    function.update_autoscaler(min_containers=min_instances)


def _dispatch_modal_generation(vote_id: str, winner_option: str) -> None:
    descriptor = _get_descriptor(winner_option)

    music_cls = modal.Cls.from_name(settings.modal_app_name, settings.modal_class_name)
    generator = music_cls()
    method = getattr(generator, settings.modal_method_name)
    method.remote(
        genre=descriptor["genre"],
        mood=descriptor["mood"],
        energy=descriptor["energy"],
        vote_id=vote_id,
    )


async def _set_min_instances(min_instances: int) -> None:
    await asyncio.to_thread(_set_modal_min_instances, min_instances)


async def _set_min_instances_zero_with_retry(vote_id: str) -> None:
    deadline = time.monotonic() + max(1, settings.scale_down_retry_horizon_seconds)
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            await _set_min_instances(0)
            logger.info("Scaled modal min_instances to 0", extra={"voteId": vote_id})
            return
        except Exception as exc:
            last_error = exc
            logger.warning("Failed to scale modal to 0; retrying", extra={"voteId": vote_id})
            await asyncio.sleep(max(1, settings.scale_down_retry_delay_seconds))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to scale modal min_instances to 0 within retry horizon")


async def _is_close_done(vote_id: str) -> bool:
    client = get_redis_client()
    return bool(await client.get(_close_done_key(vote_id)))  # type: ignore[misc]


async def _mark_close_done(vote_id: str) -> None:
    client = get_redis_client()
    await client.set(_close_done_key(vote_id), "1", ex=max(1, settings.close_done_ttl_seconds))  # type: ignore[misc]


async def _acquire_close_lock(vote_id: str) -> bool:
    client = get_redis_client()
    return bool(
        await client.set(  # type: ignore[misc]
            _close_lock_key(vote_id),
            "1",
            ex=max(1, settings.close_lock_ttl_seconds),
            nx=True,
        )
    )


async def _release_close_lock(vote_id: str) -> None:
    client = get_redis_client()
    await client.delete(_close_lock_key(vote_id))  # type: ignore[misc]


def _enqueue_warmup(vote_id: str, end_at_ms: int) -> None:
    warmup_at_ms = end_at_ms - (settings.warmup_lead_seconds * 1000)
    delay_seconds = max(0.0, (warmup_at_ms - _now_epoch_ms()) / 1000.0)

    enqueue_json_task_with_delay(
        settings.modal_queue_name,
        _warmup_url(),
        {"voteId": vote_id, "endAt": end_at_ms},
        delay_seconds,
        task_id=None,
        ignore_already_exists=True,
    )


async def _handle_open_event(message: Dict[str, Any]) -> Dict[str, str]:
    vote_id = message.get("voteId")
    if not isinstance(vote_id, str) or not vote_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voteId is required")

    try:
        end_at_ms = _parse_end_at_ms(message.get("endAt"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="endAt is required")

    if not await _has_active_listeners():
        logger.info("Skipping warmup scheduling due to no listeners", extra={"voteId": vote_id})
        return {"status": "skipped"}

    try:
        _enqueue_warmup(vote_id, end_at_ms)
    except Exception:
        logger.exception("Failed to enqueue warmup", extra={"voteId": vote_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to enqueue warmup")

    logger.info("Warmup scheduled", extra={"voteId": vote_id, "endAt": end_at_ms})
    return {"status": "ok"}


async def _handle_close_event(message: Dict[str, Any]) -> Dict[str, str]:
    vote_id = message.get("voteId")
    winner_option = message.get("winnerOption")

    if not isinstance(vote_id, str) or not vote_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voteId is required")
    if not isinstance(winner_option, str) or not winner_option.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="winnerOption is required")

    if await _is_close_done(vote_id):
        return {"status": "already_processed"}

    acquired = await _acquire_close_lock(vote_id)
    if not acquired:
        return {"status": "in_progress"}

    try:
        if not await _has_active_listeners():
            logger.info("Skipping modal generation due to no listeners", extra={"voteId": vote_id})
            await _mark_close_done(vote_id)
            return {"status": "skipped"}

        await _set_min_instances(1)
        logger.info("Scaled modal min_instances to 1", extra={"voteId": vote_id})

        await asyncio.to_thread(_dispatch_modal_generation, vote_id, winner_option)
        logger.info("Modal generation completed", extra={"voteId": vote_id, "winnerOption": winner_option})

        await _set_min_instances_zero_with_retry(vote_id)
        await _mark_close_done(vote_id)
        return {"status": "ok"}
    finally:
        await _release_close_lock(vote_id)


@app.post("/events/vote")
async def vote_event(payload: Dict[str, Any]) -> Dict[str, str]:
    message = decode_pubsub_json(payload)
    event_type = message.get("event")

    if event_type == "OPEN":
        return await _handle_open_event(message)
    if event_type == "CLOSE":
        return await _handle_close_event(message)
    return {"status": "ignored"}


@app.post("/warmup")
async def warmup(payload: Dict[str, Any]) -> Dict[str, str]:
    vote_id = payload.get("voteId")
    if not isinstance(vote_id, str) or not vote_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voteId is required")

    if not await _has_active_listeners():
        logger.info("Skipping warmup due to no listeners", extra={"voteId": vote_id})
        return {"status": "skipped"}

    try:
        await _set_min_instances(1)
    except Exception:
        logger.exception("Failed to set modal min_instances to 1", extra={"voteId": vote_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to warm modal")

    logger.info("Warmup applied", extra={"voteId": vote_id})
    return {"status": "ok"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
