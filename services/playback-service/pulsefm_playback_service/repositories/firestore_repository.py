import logging
import random
import uuid
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore
from google.cloud.firestore import SERVER_TIMESTAMP, AsyncClient, AsyncTransaction, async_transactional

from pulsefm_descriptors.data import get_descriptor_keys

from pulsefm_playback_service.config import Settings
from pulsefm_playback_service.domain.models import SongRotationResult
from pulsefm_playback_service.utils.time import utc_now


class FirestoreRepository:
    def __init__(self, db: AsyncClient, settings: Settings, logger: logging.Logger | None = None) -> None:
        self.db = db
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)

    async def get_station_state(self) -> dict[str, Any] | None:
        doc = await self.db.collection(self.settings.stations_collection).document("main").get()
        return doc.to_dict() if doc.exists else None

    async def get_current_state(self) -> dict[str, Any] | None:
        doc = await self.db.collection(self.settings.vote_state_collection).document("current").get()
        return doc.to_dict() if doc.exists else None

    async def set_current_state(self, state: dict[str, Any]) -> None:
        await self.db.collection(self.settings.vote_state_collection).document("current").set(state)

    def _build_vote(
        self,
        vote_id: str,
        start_at,
        duration_ms: int,
        options: list[str],
        version: int,
    ) -> dict[str, Any]:
        end_at = start_at + timedelta(milliseconds=duration_ms)
        return {
            "voteId": vote_id,
            "status": "OPEN",
            "startAt": start_at,
            "durationMs": duration_ms,
            "endAt": end_at,
            "options": options,
            "tallies": {option: 0 for option in options},
            "version": version,
            "createdAt": SERVER_TIMESTAMP,
        }

    def _get_window_options(self) -> list[str]:
        if self.settings.vote_options:
            return self.settings.vote_options
        options = get_descriptor_keys()
        if len(options) < self.settings.options_per_window:
            raise ValueError("Not enough descriptor options to sample window choices")
        return random.sample(options, self.settings.options_per_window)

    async def open_next_vote(self, version: int, duration_ms: int) -> dict[str, Any]:
        vote_id = str(uuid.uuid4())
        start_at = utc_now()
        window_options = self._get_window_options()
        window_doc = self._build_vote(vote_id, start_at, duration_ms, window_options, version)

        await self.set_current_state(window_doc)
        self.logger.info("Opened vote", extra={"voteId": vote_id, "version": version})
        return window_doc

    async def _select_ready_song_candidate(
        self,
        transaction: AsyncTransaction,
        songs_ref,
        current_vote_id: str | None,
    ) -> dict[str, Any] | None:
        query = (
            songs_ref
            .where("status", "==", "ready")
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(10)
        )
        ready_docs = await query.get(transaction=transaction)
        for doc in ready_docs:
            if current_vote_id and doc.id == current_vote_id:
                continue
            data = doc.to_dict() or {}
            duration_ms = data.get("durationMs")
            if duration_ms is None:
                continue
            return {"id": doc.id, "duration": duration_ms, "stubbed": False}
        return None

    async def rotate_song(self, request_version: int) -> SongRotationResult | None:
        station_ref = self.db.collection(self.settings.stations_collection).document("main")
        songs_ref = self.db.collection(self.settings.songs_collection)

        @async_transactional
        async def _txn(transaction: AsyncTransaction) -> dict[str, Any] | None:
            now = utc_now()

            station_snap = await station_ref.get(transaction=transaction)
            if not station_snap.exists:
                raise ValueError("stations/main not found")
            station = station_snap.to_dict() or {}
            current_version = int(station.get("version") or 0)
            if request_version <= current_version:
                return None

            next_data = station.get("next") or {}
            current_vote_id = next_data.get("voteId")
            current_duration = next_data.get("durationMs") or next_data.get("duration")
            if current_vote_id is None or current_duration is None:
                raise ValueError("stations/main.next is missing fields")

            duration_ms = int(current_duration)
            ends_at = now + timedelta(milliseconds=duration_ms)

            candidate_song = await self._select_ready_song_candidate(
                transaction,
                songs_ref,
                current_vote_id=str(current_vote_id) if current_vote_id is not None else None,
            )

            if candidate_song is None:
                stubbed_snap = await songs_ref.document("stubbed").get(transaction=transaction)
                if not stubbed_snap.exists:
                    raise ValueError("No ready song or stubbed song")
                stubbed_data = stubbed_snap.to_dict() or {}
                stubbed_duration = stubbed_data.get("durationMs")
                if stubbed_duration is None:
                    raise ValueError("Stubbed song missing fields")
                candidate_song = {"id": "stubbed", "duration": stubbed_duration, "stubbed": True}

            next_duration_ms = int(candidate_song["duration"])

            transaction.update(station_ref, {
                "voteId": current_vote_id,
                "startAt": now,
                "endAt": ends_at,
                "durationMs": duration_ms,
                "version": request_version,
                "next": {
                    "voteId": candidate_song["id"],
                    "duration": next_duration_ms,
                    "durationMs": next_duration_ms,
                },
            })

            if current_vote_id != "stubbed":
                transaction.update(songs_ref.document(current_vote_id), {"status": "played"})
            if not candidate_song.get("stubbed"):
                transaction.update(songs_ref.document(candidate_song["id"]), {"status": "queued"})

            return {
                "start_at": now,
                "ends_at": ends_at,
                "duration_ms": duration_ms,
                "vote_id": current_vote_id,
                "next_vote_id": candidate_song["id"],
                "next_duration_ms": next_duration_ms,
                "next_stubbed": bool(candidate_song.get("stubbed")),
                "version": request_version,
            }

        transaction = self.db.transaction()
        try:
            result = await _txn(transaction)
        except ValueError as exc:
            self.logger.exception("Playback transaction failed")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
        except Exception:
            self.logger.exception("Playback transaction failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to run playback transaction",
            )

        if result is None:
            return None
        return SongRotationResult(**result)

    async def refresh_next_song(self, trigger_vote_id: str) -> dict[str, Any]:
        station_ref = self.db.collection(self.settings.stations_collection).document("main")
        songs_ref = self.db.collection(self.settings.songs_collection)

        @async_transactional
        async def _transaction_fn(transaction: AsyncTransaction) -> dict[str, Any]:
            station_snap = await station_ref.get(transaction=transaction)
            if not station_snap.exists:
                raise ValueError("stations/main not found")
            station = station_snap.to_dict() or {}
            current_vote_id = station.get("voteId")
            next_data = station.get("next") or {}
            next_vote_id = next_data.get("voteId")
            station_version = int(station.get("version") or 0)

            if next_vote_id != "stubbed":
                existing_duration = next_data.get("durationMs") or next_data.get("duration")
                if existing_duration is None:
                    raise ValueError("stations/main.next missing duration")
                return {
                    "action": "noop",
                    "reason": "next_not_stubbed",
                    "voteId": next_vote_id,
                    "durationMs": int(existing_duration),
                    "version": station_version,
                }

            candidate_song = await self._select_ready_song_candidate(
                transaction,
                songs_ref,
                current_vote_id=str(current_vote_id) if current_vote_id is not None else None,
            )
            if candidate_song is None:
                return {
                    "action": "noop",
                    "reason": "no_ready_song",
                    "voteId": next_vote_id,
                    "version": station_version,
                }

            duration_ms = int(candidate_song["duration"])
            vote_id = str(candidate_song["id"])
            transaction.update(station_ref, {
                "next": {
                    "voteId": vote_id,
                    "duration": duration_ms,
                    "durationMs": duration_ms,
                },
            })
            transaction.update(songs_ref.document(vote_id), {"status": "queued"})
            return {"action": "updated", "voteId": vote_id, "durationMs": duration_ms, "version": station_version}

        transaction = self.db.transaction()
        try:
            return await _transaction_fn(transaction)
        except ValueError as exc:
            self.logger.exception("Failed to refresh next song")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
        except Exception:
            self.logger.exception("Failed to refresh next song", extra={"voteId": trigger_vote_id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to refresh next song",
            )
