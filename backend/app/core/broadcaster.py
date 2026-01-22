import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Broadcaster(ABC):
    """Abstract base class for broadcasting audio chunks."""
    
    @abstractmethod
    async def publish_chunk(self, chunk: bytes) -> None:
        """
        Publish an audio chunk to the broadcaster.
        
        Args:
            chunk: Audio data chunk in bytes
        """
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Start the broadcaster."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the broadcaster and clean up resources."""
        pass


class PlaceholderBroadcaster(Broadcaster):
    """
    Placeholder broadcaster implementation that logs chunks.
    This will be replaced with a real broadcaster implementation later.
    """
    
    def __init__(self):
        self._running = False
        self._chunk_count = 0
        self._total_bytes = 0
    
    async def start(self) -> None:
        """Start the placeholder broadcaster."""
        self._running = True
        self._chunk_count = 0
        self._total_bytes = 0
        logger.info("Placeholder broadcaster started")
    
    async def stop(self) -> None:
        """Stop the placeholder broadcaster."""
        self._running = False
        logger.info(f"Placeholder broadcaster stopped. Processed {self._chunk_count} chunks, {self._total_bytes} bytes total")
    
    async def publish_chunk(self, chunk: bytes) -> None:
        """
        Publish an audio chunk (placeholder - just logs).
        
        Args:
            chunk: Audio data chunk in bytes
        """
        if not self._running:
            logger.warning("Broadcaster not running, ignoring chunk")
            return
        
        chunk_size = len(chunk)
        self._chunk_count += 1
        self._total_bytes += chunk_size
        
        # Log periodically to avoid spam
        if self._chunk_count % 100 == 0:
            logger.debug(f"Broadcaster received chunk #{self._chunk_count} ({chunk_size} bytes, {self._total_bytes} total)")

