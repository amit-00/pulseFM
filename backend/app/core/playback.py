import asyncio
import logging
from typing import Optional

from app.core.scheduler import TrackScheduler
from app.core.broadcaster import StreamBroadcaster
from app.models.request import ReadyRequest
from app.services.encoder import encode_stream, OutputFormat

logger = logging.getLogger(__name__)


class PlaybackEngine:
    """Playback engine that continuously processes tracks from the queue."""
    
    def __init__(
        self,
        scheduler: TrackScheduler,
        broadcaster: Optional[StreamBroadcaster] = None,
        chunk_size: int = 8192
    ):
        """
        Initialize the playback engine.
        
        Args:
            scheduler: TrackScheduler instance to get tracks from
            broadcaster: StreamBroadcaster instance (defaults to StreamBroadcaster)
            chunk_size: Size of chunks to read from ffmpeg stdout (default: 8KB)
        """
        self.scheduler = scheduler
        self.broadcaster = broadcaster or StreamBroadcaster()
        self.chunk_size = chunk_size
        self._running = False
        self._playback_task: Optional[asyncio.Task] = None
        self._current_track: Optional[ReadyRequest] = None

        self.audio_bitrate = 128000
        self.audio_bytes_per_second = self.audio_bitrate / 8
    
    async def start(self):
        """Start the playback engine."""
        if self._running:
            logger.warning("Playback engine is already running")
            return
        
        self._running = True
        logger.info("Starting playback engine...")
        
        # Start playback loop
        self._playback_task = asyncio.create_task(self._playback_loop())
        
        logger.info("Playback engine started")
    
    async def stop(self):
        """Stop the playback engine and clean up resources."""
        if not self._running:
            return
        
        logger.info("Stopping playback engine...")
        self._running = False
        
        # Stop current playback if any
        await self._stop_current_playback()
        
        # Cancel playback task
        if self._playback_task:
            self._playback_task.cancel()
            try:
                await self._playback_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Playback engine stopped")
    
    async def _playback_loop(self):
        """Main playback loop that continuously processes tracks."""
        while self._running:
            try:
                # Check if there's a track available
                track = await self.scheduler.get_next_track()
                
                if track is None:
                    # No track available, wait a bit before checking again
                    await asyncio.sleep(0.5)
                    continue
                
                # Pop the track from the queue
                await self.scheduler.remove_track()
                self._current_track = track
                
                logger.info(f"Starting playback of track {track.request_id}")
                
                # Process the track
                await self._process_track(track)
                
                logger.info(f"Finished playback of track {track.request_id}")
                self._current_track = None
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in playback loop: {e}", exc_info=True)
                # Wait a bit before retrying
                await asyncio.sleep(1)
    
    async def _process_track(self, track: ReadyRequest):
        """
        Process a single track: encode and stream using the encoder service.
        
        Args:
            track: ReadyRequest to process
        """
        try:
            logger.debug(f"Starting encoding for track {track.request_id}")
            
            # Use encoder service to get encoded audio chunks
            async for chunk in encode_stream(
                blob_path=track.audio_url,
                output_format=OutputFormat.ADTS,
                bitrate=self.audio_bitrate,
                sample_rate=44100,
                channels=2,
                chunk_size=self.chunk_size
            ):
                # Stream chunks with rate limiting
                await self._stream_chunk(chunk)
            
            logger.debug(f"Encoding completed successfully for track {track.request_id}")
            
        except Exception as e:
            logger.error(f"Error processing track {track.request_id}: {e}", exc_info=True)
            raise
    
    async def _stream_chunk(self, chunk: bytes):
        """
        Stream a single chunk to the broadcaster with rate limiting.
        
        Args:
            chunk: Audio data chunk to publish
        """
        if not self._running:
            return
        
        chunk_size = len(chunk)
        chunk_seconds = chunk_size / self.audio_bytes_per_second

        start_time = asyncio.get_event_loop().time()
        
        # Publish chunk to broadcaster 
        await self.broadcaster.publish_chunk(chunk)

        publish_delay = asyncio.get_event_loop().time() - start_time

        await asyncio.sleep(chunk_seconds - publish_delay)
    
    async def _stop_current_playback(self):
        """Stop the current playback if any."""
        logger.debug("Stop current playback requested (cleanup handled by encoder)")


# Singleton instance
playback_engine_instance: Optional[PlaybackEngine] = None


def get_playback_engine(
    scheduler: Optional[TrackScheduler] = None,
    broadcaster: Optional[StreamBroadcaster] = None
) -> PlaybackEngine:
    """Get or create the singleton playback engine instance."""
    global playback_engine_instance
    
    if playback_engine_instance is None:
        if scheduler is None:
            from app.core.scheduler import get_scheduler
            scheduler = get_scheduler()
        
        playback_engine_instance = PlaybackEngine(scheduler, broadcaster)
    
    return playback_engine_instance
