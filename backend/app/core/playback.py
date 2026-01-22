import asyncio
import logging
from typing import Optional
from google.cloud.firestore import AsyncClient

from app.core.scheduler import TrackScheduler
from app.core.broadcaster import Broadcaster, PlaceholderBroadcaster
from app.models.request import ReadyRequest
from app.services.storage import generate_signed_url

logger = logging.getLogger(__name__)


class PlaybackEngine:
    """Playback engine that continuously processes tracks from the queue."""
    
    def __init__(
        self,
        scheduler: TrackScheduler,
        broadcaster: Optional[Broadcaster] = None,
        chunk_size: int = 8192
    ):
        """
        Initialize the playback engine.
        
        Args:
            scheduler: TrackScheduler instance to get tracks from
            broadcaster: Broadcaster instance (defaults to PlaceholderBroadcaster)
            chunk_size: Size of chunks to read from ffmpeg stdout (default: 8KB)
        """
        self.scheduler = scheduler
        self.broadcaster = broadcaster or PlaceholderBroadcaster()
        self.chunk_size = chunk_size
        self._running = False
        self._playback_task: Optional[asyncio.Task] = None
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._current_track: Optional[ReadyRequest] = None
    
    async def start(self):
        """Start the playback engine."""
        if self._running:
            logger.warning("Playback engine is already running")
            return
        
        self._running = True
        logger.info("Starting playback engine...")
        
        # Start broadcaster
        await self.broadcaster.start()
        
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
        
        # Stop broadcaster
        await self.broadcaster.stop()
        
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
        Process a single track: generate signed URL, transcode, and stream.
        
        Args:
            track: ReadyRequest to process
        """
        signed_url = None
        process = None
        
        try:
            # Generate signed URL from GCS blob path
            logger.debug(f"Generating signed URL for {track.audio_url}")
            signed_url = generate_signed_url(track.audio_url, expiration_seconds=3600)
            logger.debug(f"Generated signed URL (length: {len(signed_url)})")
            
            # Launch ffmpeg subprocess
            # Command: ffmpeg -i <signed_url> -f adts -acodec aac -b:a 128k -ar 44100 -ac 2 -
            # -f adts: Output format is AAC ADTS
            # -acodec aac: Audio codec is AAC
            # -b:a 128k: Audio bitrate 128kbps
            # -ar 44100: Sample rate 44.1kHz
            # -ac 2: Stereo (2 channels)
            # -: Output to stdout
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", signed_url,
                "-f", "adts",
                "-acodec", "aac",
                "-b:a", "128k",
                "-ar", "44100",
                "-ac", "2",
                "-"  # Output to stdout
            ]
            
            logger.debug(f"Launching ffmpeg: {' '.join(ffmpeg_cmd[:3])} <url> ...")
            
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            self._current_process = process
            
            # Read chunks from ffmpeg stdout and publish to broadcaster
            await self._stream_chunks(process)
            
            # Wait for process to complete
            return_code = await process.wait()
            
            if return_code != 0:
                # Read stderr for error details
                stderr_output = await process.stderr.read()
                error_msg = stderr_output.decode('utf-8', errors='ignore')
                logger.error(f"FFmpeg process failed with return code {return_code}: {error_msg}")
                raise RuntimeError(f"FFmpeg transcoding failed: {error_msg}")
            
            logger.debug(f"FFmpeg process completed successfully for track {track.request_id}")
            
        except Exception as e:
            logger.error(f"Error processing track {track.request_id}: {e}", exc_info=True)
            raise
        finally:
            # Cleanup: kill process if still running
            if process and process.returncode is None:
                logger.warning(f"Terminating ffmpeg process for track {track.request_id}")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(f"FFmpeg process did not terminate, killing it")
                    process.kill()
                    await process.wait()
            
            self._current_process = None
    
    async def _stream_chunks(self, process: asyncio.subprocess.Process):
        """
        Read chunks from ffmpeg stdout and publish to broadcaster.
        
        Args:
            process: FFmpeg subprocess with stdout pipe
        """
        if process.stdout is None:
            raise ValueError("Process stdout is None")
        
        try:
            while self._running:
                chunk = await process.stdout.read(self.chunk_size)
                
                if not chunk:
                    # EOF reached
                    break
                
                # Publish chunk to broadcaster
                await self.broadcaster.publish_chunk(chunk)
                
        except Exception as e:
            logger.error(f"Error streaming chunks: {e}", exc_info=True)
            raise
    
    async def _stop_current_playback(self):
        """Stop the current playback if any."""
        if self._current_process and self._current_process.returncode is None:
            logger.info("Stopping current playback...")
            self._current_process.terminate()
            try:
                await asyncio.wait_for(self._current_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Process did not terminate, killing it")
                self._current_process.kill()
                await self._current_process.wait()
            self._current_process = None


# Singleton instance
playback_engine_instance: Optional[PlaybackEngine] = None


def get_playback_engine(
    scheduler: Optional[TrackScheduler] = None,
    broadcaster: Optional[Broadcaster] = None
) -> PlaybackEngine:
    """Get or create the singleton playback engine instance."""
    global playback_engine_instance
    
    if playback_engine_instance is None:
        if scheduler is None:
            from app.core.scheduler import get_scheduler
            scheduler = get_scheduler()
        
        playback_engine_instance = PlaybackEngine(scheduler, broadcaster)
    
    return playback_engine_instance
