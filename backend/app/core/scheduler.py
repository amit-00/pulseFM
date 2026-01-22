import asyncio
import logging
from collections import deque
from typing import Optional, Dict
from google.cloud.firestore import AsyncClient, FieldFilter

from app.models.request import ReadyRequest, RequestStatus

logger = logging.getLogger(__name__)


MIN_BUFFER_SIZE = 3


class TrackScheduler:
    """Scheduling engine that manages the upcoming tracks queue."""
    
    def __init__(self, db: AsyncClient):
        self.db = db
        self.queue: deque = deque()
        self.queue_lock = asyncio.Lock()
        self._listener_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._monitor_interval = 5  # Check queue depth every 5 seconds
        
    async def start(self):
        """Start the scheduler and begin listening to Firestore changes."""
        if self._running:
            logger.warning("Scheduler is already running")
            return
            
        self._running = True
        logger.info("Starting track scheduler...")
        
        # Start Firestore listener
        self._listener_task = asyncio.create_task(self._listen_to_requests())
        
        # Start queue monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_queue_depth())
        
        logger.info("Track scheduler started")
        
    async def stop(self):
        """Stop the scheduler and clean up resources."""
        if not self._running:
            return
            
        logger.info("Stopping track scheduler...")
        self._running = False
        
        # Cancel tasks
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
                
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Track scheduler stopped")
        
    async def _listen_to_requests(self):
        """Listen to Firestore 'requests' collection for documents with status='ready'."""
        poll_interval = 2  # Poll every 2 seconds
        
        # Initial load of existing ready requests
        try:
            query = self.db.collection("requests").where(
                filter=FieldFilter("status", "==", RequestStatus.READY)
            )
            docs = await query.get()
            for doc in docs:
                data = doc.to_dict()
                if data:
                    await self._add_ready_track(data, doc.id)
            logger.info(f"Initial load: found {len(docs)} ready requests")
        except Exception as e:
            logger.error(f"Error in initial load of ready requests: {e}", exc_info=True)
        
        # Poll for new ready requests
        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                
                # Query for ready requests
                query = self.db.collection("requests").where(
                    filter=FieldFilter("status", "==", RequestStatus.READY)
                )
                docs = await query.get()
                
                # Process all ready requests (status update prevents duplicates)
                for doc in docs:
                    data = doc.to_dict()
                    if data:
                        await self._add_ready_track(data, doc.id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error polling Firestore for ready requests: {e}", exc_info=True)
                await asyncio.sleep(poll_interval)
                
    async def _add_ready_track(self, data: Dict, doc_id: Optional[str] = None):
        """Add a ready track to the queue and update its status to 'queued'."""
        try:
            request_id = data.get("request_id") or doc_id
            if not request_id:
                logger.warning("Received document without request_id, skipping")
                return
                
            # Check if already in queue
            async with self.queue_lock:
                if any(track.request_id == request_id for track in self.queue):
                    logger.debug(f"Request {request_id} already in queue, skipping")
                    return
                    
            # Validate required fields
            if not data.get("audio_url"):
                logger.warning(f"Request {request_id} missing audio_url, skipping")
                return
                
            # Create ReadyRequest model
            try:
                ready_request = ReadyRequest(
                    request_id=request_id,
                    genre=data.get("genre"),
                    mood=data.get("mood"),
                    energy=data.get("energy", "mid"),
                    status=RequestStatus.QUEUED,  # Will be queued after adding
                    created_at=data.get("created_at", ""),
                    audio_url=data.get("audio_url"),
                    stubbed=data.get("stubbed", False)
                )
            except Exception as e:
                logger.error(f"Error creating ReadyRequest for {request_id}: {e}")
                return
                
            # Update Firestore document status to 'queued' before adding to queue
            # Use doc_id if provided, otherwise use request_id as document ID
            doc_ref = self.db.collection("requests").document(doc_id or request_id)
            try:
                await doc_ref.update({"status": RequestStatus.QUEUED})
            except Exception as e:
                logger.error(f"Error updating status to 'queued' for {request_id}: {e}")
                # Continue anyway - the track might have been updated by another process
                
            # Add to queue
            async with self.queue_lock:
                # Double-check not already in queue (race condition protection)
                if not any(track.request_id == request_id for track in self.queue):
                    self.queue.append(ready_request)
                    logger.info(f"Added track {request_id} to queue (queue size: {len(self.queue)})")
                    
        except Exception as e:
            logger.error(f"Error adding ready track to queue: {e}", exc_info=True)
            
    async def _monitor_queue_depth(self):
        """Monitor queue depth and fetch stubs when needed."""
        while self._running:
            try:
                await asyncio.sleep(self._monitor_interval)
                
                async with self.queue_lock:
                    queue_size = len(self.queue)
                    
                if queue_size < MIN_BUFFER_SIZE:
                    needed = MIN_BUFFER_SIZE - queue_size
                    logger.info(f"Queue depth ({queue_size}) below minimum ({MIN_BUFFER_SIZE}), fetching {needed} stub(s)")
                    
                    for _ in range(needed):
                        await self._fetch_stub_track()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue monitoring: {e}", exc_info=True)
                await asyncio.sleep(self._monitor_interval)
                
    async def _fetch_stub_track(self):
        """Fetch a stub track from the 'stubbed' collection."""
        try:
            # Query stubbed collection
            stubbed_ref = self.db.collection("stubbed")
            docs = await stubbed_ref.limit(100).get()  # Get up to 100, then pick one
            
            if not docs:
                logger.warning("No stubbed tracks available in Firestore")
                return
                
            # Convert to list and pick first available (or could randomize)
            stubbed_docs = list(docs)
            if not stubbed_docs:
                return
                
            # Try to find a stub that's not already in the queue
            for doc in stubbed_docs:
                data = doc.to_dict()
                
                if not data:
                    continue
                    
                request_id = data.get("request_id") or doc.id
                
                # Check if already in queue
                async with self.queue_lock:
                    if any(track.request_id == request_id for track in self.queue):
                        continue  # Try next stub
                
                # Create ReadyRequest with stubbed=True
                try:
                    ready_request = ReadyRequest(
                        request_id=request_id,
                        genre=data.get("genre", "rock"),
                        mood=data.get("mood", "happy"),
                        energy=data.get("energy", "mid"),
                        status=RequestStatus.QUEUED,
                        created_at=data.get("created_at", ""),
                        audio_url=data.get("audio_url", ""),
                        stubbed=True
                    )
                except Exception as e:
                    logger.error(f"Error creating ReadyRequest for stub {request_id}: {e}")
                    continue  # Try next stub
                
                # Add to queue
                async with self.queue_lock:
                    # Double-check not already in queue (race condition protection)
                    if not any(track.request_id == request_id for track in self.queue):
                        self.queue.append(ready_request)
                        logger.info(f"Added stub track {request_id} to queue (queue size: {len(self.queue)})")
                        return  # Successfully added one stub
                
            logger.debug("All available stubs are already in the queue")
                    
        except Exception as e:
            logger.error(f"Error fetching stub track: {e}", exc_info=True)
            
    async def get_next_track(self) -> Optional[ReadyRequest]:
        """Get the next track from the queue without removing it."""
        async with self.queue_lock:
            if len(self.queue) > 0:
                return self.queue[0]
            return None
            
    async def remove_track(self, request_id: Optional[str] = None):
        """Remove a track from the queue. If request_id is None, removes the first track."""
        async with self.queue_lock:
            if len(self.queue) == 0:
                return
                
            if request_id:
                # Remove specific track by request_id
                original_size = len(self.queue)
                self.queue = deque([t for t in self.queue if t.request_id != request_id])
                removed = original_size - len(self.queue)
                if removed > 0:
                    logger.info(f"Removed track {request_id} from queue (queue size: {len(self.queue)})")
            else:
                # Remove first track
                if len(self.queue) > 0:
                    removed_track = self.queue.popleft()
                    logger.info(f"Removed track {removed_track.request_id} from queue (queue size: {len(self.queue)})")
                    
    async def get_queue_size(self) -> int:
        """Get the current queue size."""
        async with self.queue_lock:
            return len(self.queue)
            
    async def get_queue_state(self) -> Dict:
        """Get the current queue state for API responses."""
        async with self.queue_lock:
            if len(self.queue) == 0:
                return {
                    "now_playing": None,
                    "next_up": []
                }
                
            queue_list = list(self.queue)
            return {
                "now_playing": queue_list[0].request_id if queue_list else None,
                "next_up": [track.request_id for track in queue_list[1:]]
            }


# Singleton instance
scheduler_instance: Optional[TrackScheduler] = None


def get_scheduler(db: Optional[AsyncClient] = None) -> TrackScheduler:
    """Get or create the singleton scheduler instance."""
    global scheduler_instance
    
    if scheduler_instance is None:
        if db is None:
            from app.services.db import db as default_db
            db = default_db
        scheduler_instance = TrackScheduler(db)
        
    return scheduler_instance

