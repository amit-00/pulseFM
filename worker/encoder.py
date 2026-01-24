import asyncio
import logging
from enum import Enum
from typing import AsyncIterator
from io import BytesIO

from pydub import AudioSegment

logger = logging.getLogger(__name__)


class OutputFormat(str, Enum):
    """Output format for audio encoding."""
    ADTS = "adts"  # AAC in ADTS container
    M4A = "m4a"    # Opus in M4A container


async def encode_stream(
    file_url: str,
    output_format: OutputFormat = OutputFormat.ADTS,
    bitrate: int = 128000,
    sample_rate: int = 44100,
    channels: int = 2,
    chunk_size: int = 8192
) -> AsyncIterator[bytes]:
    """
    Encode audio from a file URL and stream chunks asynchronously using pydub.
    """
    try:
        logger.debug(f"Encoding audio from file URL: {file_url}")
        
        # Load audio file using pydub
        def load_and_encode():
            # Load the audio file
            audio = AudioSegment.from_file(file_url)
            
            # Apply transformations
            # Set sample rate
            if audio.frame_rate != sample_rate:
                audio = audio.set_frame_rate(sample_rate)
            
            # Set channels (mono/stereo)
            if channels == 1:
                audio = audio.set_channels(1)
            elif channels == 2:
                audio = audio.set_channels(2)
            
            # Convert bitrate from bits per second to kbps for pydub
            bitrate_kbps = f"{bitrate // 1000}k"
            
            # Export to BytesIO buffer based on format
            buffer = BytesIO()
            
            if output_format == OutputFormat.ADTS:
                # AAC in ADTS container
                audio.export(
                    buffer,
                    format="adts",
                    codec="aac",
                    bitrate=bitrate_kbps
                )
            elif output_format == OutputFormat.M4A:
                # Opus in M4A container
                audio.export(
                    buffer,
                    format="mp4",
                    codec="aac",
                    bitrate=bitrate_kbps
                )
            
            # Get the encoded data
            buffer.seek(0)
            return buffer.read()
        
        # Run encoding in a thread pool to avoid blocking
        encoded_data = await asyncio.to_thread(load_and_encode)
        
        logger.debug(f"Successfully encoded audio, streaming {len(encoded_data)} bytes")
        
        # Stream the encoded data in chunks
        offset = 0
        while offset < len(encoded_data):
            chunk = encoded_data[offset:offset + chunk_size]
            if not chunk:
                break
            yield chunk
            offset += chunk_size
        
        logger.debug(f"Finished streaming encoded audio")
        
    except Exception as e:
        logger.error(f"Error encoding audio from {file_url}: {e}", exc_info=True)
        raise RuntimeError(f"Audio encoding failed: {str(e)}")
