import asyncio
import logging
from collections import deque
from typing import Dict

from google.cloud.firestore import AsyncClient, FieldFilter, Query

from pulsefm_models.request import ReadyRequest, RequestStatus

logger = logging.getLogger(__name__)


MINIMUM_DEPTH = 3


class Station:
    def __init__(self, db: AsyncClient):
        self.db = db
        self._is_running = False
        self.now_playing = None
        self.track_start_time = None
        self.duration_elapsed_ms = 0

        self.queue = deque()
        self.queue_lock = asyncio.Lock()
        self.tracks_in_queue = set[str]()

        self._playback_task = None
        self._listen_task = None

    async def start(self) -> None:
        if self._is_running:
            logger.warning("Station is already running")
            return
        
        self._is_running = True
        self._playback_task = asyncio.create_task(self._playback_loop())
        self._listen_task = asyncio.create_task(self._listen_to_requests())
        logger.info("Station started")

    async def stop(self) -> None:
        if not self._is_running:
            return
        
        if self._playback_task:
            self._playback_task.cancel()
            try:
                await self._playback_task
            except asyncio.CancelledError:
                pass
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        self._is_running = False

    def get_now_playing(self) -> ReadyRequest | None:
        return self.now_playing

    def get_duration_elapsed_ms(self) -> int:
        return self.duration_elapsed_ms

    async def get_queue_size(self) -> int:
        async with self.queue_lock:
            return len(self.queue)

    async def get_next_track(self) -> ReadyRequest | None:
        async with self.queue_lock:
            if len(self.queue) > 0:
                return self.queue[0]
            return None

    async def _playback_loop(self) -> None:
        logger.info("Playing tracks")
        while self._is_running:
            track: ReadyRequest | None = None
            
            async with self.queue_lock:
                if len(self.queue) > 0:
                    track = self.queue.popleft()
                else:
                    track = None

            if track is None:
                await asyncio.sleep(0.1)
                continue

            self.now_playing = track
            self.track_start_time = asyncio.get_event_loop().time()
            self.duration_elapsed_ms = 0
            self.tracks_in_queue.discard(track.request_id)

            while self.duration_elapsed_ms < track.duration_ms:
                elapsed = int((asyncio.get_event_loop().time()- self.track_start_time) * 1000)
                self.duration_elapsed_ms = elapsed
                await asyncio.sleep(0.1)
            
            self.now_playing = None
            self.track_start_time = None
    
    async def _listen_to_requests(self) -> None:
        logger.info("Listening to requests")
        while self._is_running:
            query = (
                self.db.collection("requests")
                .where(filter=FieldFilter("status", "==", RequestStatus.READY))
                .order_by("created_at", direction=Query.ASCENDING)
            )

            docs = await query.get()
            for doc in docs:
                data = doc.to_dict()
                if data:
                    await self._add_ready_track(data)

            async with self.queue_lock:
                queue_size = len(self.queue)
                needed = 0
                if queue_size < MINIMUM_DEPTH:
                    needed = MINIMUM_DEPTH - queue_size
                    logger.info(f"Queue depth ({queue_size}) below minimum ({MINIMUM_DEPTH}), fetching {needed} stub(s)")

            if needed > 0:                    
                logger.info(f"Fetching {needed} stub(s)")
                await self._add_stub_tracks(needed)

            await asyncio.sleep(1)

    async def _add_ready_track(self, data: Dict) -> None:
        request_id = data.get("request_id")
        if not request_id:
            return

        request = ReadyRequest(**data)

        async with self.queue_lock:
            if request_id not in self.tracks_in_queue:
                self.tracks_in_queue.add(request_id)
                self.queue.append(request)

        doc_ref = self.db.collection("requests").document(request_id)
        try:
            await doc_ref.update({"status": RequestStatus.QUEUED})
        except Exception as e:
            logger.error(f"Error updating status to 'queued' for {request_id}: {e}")

    async def _add_stub_tracks(self, needed: int) -> None:
        collection = await self.db.collection("stubbed").get()
        if not collection:
            return

        to_add = []
        for doc in collection:
            if len(to_add) >= needed:
                break

            if doc.id in self.tracks_in_queue:
                continue

            to_add.append(doc)

        for doc in to_add:
            data = doc.to_dict()
            if not data:
                logger.error(f"No data found for stubbed track {doc.id}")
                continue
            try:
                request = ReadyRequest(**data)
            except Exception as e:
                logger.error(f"Error creating ReadyRequest from stubbed track {doc.id}: {e}")
                continue

            async with self.queue_lock:
                self.tracks_in_queue.add(request.request_id)
                self.queue.append(request)
