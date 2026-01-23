import asyncio
import logging
from enum import Enum
from typing import AsyncIterator, List

from app.services.storage import generate_signed_url

logger = logging.getLogger(__name__)


class OutputFormat(str, Enum):
    """Output format for audio encoding."""
    ADTS = "adts"  # AAC in ADTS container
    M4A = "m4a"    # Opus in M4A container


def _build_ffmpeg_command(
    signed_url: str,
    output_format: OutputFormat,
    bitrate: int,
    sample_rate: int,
    channels: int
) -> List[str]:
    """
    Build ffmpeg command based on output format and parameters.
    """
    # Convert bitrate from bits per second to kbps for ffmpeg
    bitrate_kbps = f"{bitrate // 1000}k"
    
    # Base command arguments
    cmd = [
        "ffmpeg",
        "-i", signed_url,
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-b:a", bitrate_kbps,
    ]
    
    # Add format-specific parameters
    if output_format == OutputFormat.ADTS:
        # AAC in ADTS container
        cmd.extend([
            "-f", "adts",
            "-acodec", "aac",
        ])
    elif output_format == OutputFormat.M4A:
        # Opus in M4A container
        cmd.extend([
            "-f", "mp4",
            "-acodec", "libopus",
        ])
    else:
        raise ValueError(f"Unsupported output format: {output_format}")
    
    # Output to stdout
    cmd.append("-")
    
    return cmd


async def encode_stream(
    blob_path: str,
    output_format: OutputFormat = OutputFormat.ADTS,
    bitrate: int = 128000,
    sample_rate: int = 44100,
    channels: int = 2,
    chunk_size: int = 8192,
    expiration_seconds: int = 3600
) -> AsyncIterator[bytes]:
    """
    Encode audio from a GCS blob and stream chunks asynchronously.
    """
    signed_url = None
    process = None
    
    try:
        # Generate signed URL from GCS blob path
        logger.debug(f"Generating signed URL for {blob_path}")
        signed_url = generate_signed_url(blob_path, expiration_seconds=expiration_seconds)
        logger.debug(f"Generated signed URL (length: {len(signed_url)})")
        
        # Build ffmpeg command based on output format
        ffmpeg_cmd = _build_ffmpeg_command(
            signed_url=signed_url,
            output_format=output_format,
            bitrate=bitrate,
            sample_rate=sample_rate,
            channels=channels
        )
        
        logger.debug(f"Launching ffmpeg: {' '.join(ffmpeg_cmd[:3])} <url> ...")
        
        # Launch ffmpeg subprocess
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Read chunks from ffmpeg stdout and yield them
        if process.stdout is None:
            raise ValueError("Process stdout is None")
        
        while True:
            chunk = await process.stdout.read(chunk_size)
            
            if not chunk:
                # EOF reached
                break
            
            yield chunk
        
        # Wait for process to complete
        return_code = await process.wait()
        
        if return_code != 0:
            # Read stderr for error details
            stderr_output = await process.stderr.read()
            error_msg = stderr_output.decode('utf-8', errors='ignore')
            logger.error(f"FFmpeg process failed with return code {return_code}: {error_msg}")
            raise RuntimeError(f"FFmpeg transcoding failed: {error_msg}")
        
        logger.debug(f"FFmpeg process completed successfully")
        
    except Exception as e:
        logger.error(f"Error encoding audio from {blob_path}: {e}", exc_info=True)
        raise
    finally:
        # Cleanup: kill process if still running
        if process and process.returncode is None:
            logger.warning(f"Terminating ffmpeg process")
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"FFmpeg process did not terminate, killing it")
                process.kill()
                await process.wait()
