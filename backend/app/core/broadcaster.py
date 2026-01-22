import asyncio
import logging
import uuid
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class StreamBroadcaster():
    """
    Broadcaster implementation that maintains subscriber queues and fans out audio chunks.
    """
    
    def __init__(self, queue_maxsize: int = 10):
        """
        Initialize the stream broadcaster.
        
        Args:
            queue_maxsize: Maximum size of each subscriber queue (default: 10 chunks)
        """
        self.queue_maxsize = queue_maxsize
        self._subscribers: Dict[str, asyncio.Queue] = {}
        self._running = False
        self._lock = asyncio.Lock()
        self._subscriber_count = 0
    
    async def start(self) -> None:
        """Start the broadcaster and initialize subscriber registry."""
        async with self._lock:
            if self._running:
                logger.warning("Broadcaster is already running")
                return
            
            self._running = True
            self._subscribers = {}
            self._subscriber_count = 0
            logger.info("Stream broadcaster started")
    
    async def stop(self) -> None:
        """Stop the broadcaster and clean up all subscriber queues."""
        async with self._lock:
            if not self._running:
                return
            
            self._running = False
            
            # Close all subscriber queues
            subscriber_count = len(self._subscribers)
            for subscriber_id, queue in self._subscribers.items():
                # Put a sentinel value to signal queue closure
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            
            self._subscribers.clear()
            self._subscriber_count = 0
            logger.info(f"Stream broadcaster stopped. Cleaned up {subscriber_count} subscribers")
    
    async def publish_chunk(self, chunk: bytes) -> None:
        """
        Publish an audio chunk to all subscribers.
        Drops slow listeners whose queues are full (backpressure).
        
        Args:
            chunk: Audio data chunk in bytes
        """
        if not self._running:
            logger.warning("Broadcaster not running, ignoring chunk")
            return
        
        if not chunk:
            return
        
        # Get a snapshot of current subscribers to avoid holding lock during fan-out
        async with self._lock:
            subscribers = dict(self._subscribers)
        
        # Fan-out chunk to all subscribers
        dropped_subscribers = []
        for subscriber_id, queue in subscribers.items():
            try:
                queue.put_nowait(chunk)
            except asyncio.QueueFull:
                # Backpressure: queue is full, drop this subscriber
                logger.warning(f"Subscriber {subscriber_id} queue is full, dropping subscriber")
                dropped_subscribers.append(subscriber_id)
            except Exception as e:
                logger.error(f"Error publishing chunk to subscriber {subscriber_id}: {e}")
                dropped_subscribers.append(subscriber_id)
        
        # Remove dropped subscribers
        if dropped_subscribers:
            async with self._lock:
                for subscriber_id in dropped_subscribers:
                    if subscriber_id in self._subscribers:
                        del self._subscribers[subscriber_id]
                        self._subscriber_count -= 1
                        logger.info(f"Removed subscriber {subscriber_id} (total subscribers: {self._subscriber_count})")
    
    async def subscribe(self) -> Tuple[str, asyncio.Queue]:
        """
        Subscribe a new listener and return their subscriber ID and queue.
        
        Returns:
            Tuple of (subscriber_id, queue) where queue is an asyncio.Queue
        """
        if not self._running:
            raise RuntimeError("Broadcaster is not running")
        
        subscriber_id = str(uuid.uuid4())
        queue = asyncio.Queue(maxsize=self.queue_maxsize)
        
        async with self._lock:
            self._subscribers[subscriber_id] = queue
            self._subscriber_count += 1
            logger.info(f"Subscriber {subscriber_id} connected (total subscribers: {self._subscriber_count})")
        
        return subscriber_id, queue
    
    async def unsubscribe(self, subscriber_id: str) -> None:
        """
        Unsubscribe a listener and clean up their queue.
        
        Args:
            subscriber_id: ID of the subscriber to remove
        """
        async with self._lock:
            if subscriber_id in self._subscribers:
                del self._subscribers[subscriber_id]
                self._subscriber_count -= 1
                logger.info(f"Subscriber {subscriber_id} disconnected (total subscribers: {self._subscriber_count})")
    
    async def get_subscriber_count(self) -> int:
        """Get the current number of active subscribers."""
        async with self._lock:
            return self._subscriber_count

