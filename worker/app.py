"""Modal worker for PulseFM music generation."""
import logging
import modal
import tempfile
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
CHECKPOINT_DIR = "/checkpoints/ACE-Step/ACE-Step-v1-3.5B"
GENERATION_DURATION_SEC = 150

# BPM settings for each energy level - keeps tempo consistent
ENERGY_BPM = {
    "low": 70,    # Slow, dreamy lofi
    "mid": 85,    # Classic study beats tempo
    "high": 100,  # Upbeat but still lofi
}

app = modal.App("pulsefm-worker")


def download_models():
    """Download ACE-Step models during image build."""
    from huggingface_hub import snapshot_download
    
    snapshot_download(
        repo_id="ACE-Step/ACE-Step-v1-3.5B",
        local_dir="/checkpoints/ACE-Step/ACE-Step-v1-3.5B"
    )


# Build image with CUDA, ffmpeg, and ACE-Step
# Using the same setup as Modal's official example
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "torch==2.8.0",
        "torchaudio==2.8.0",
        "huggingface-hub",
        "git+https://github.com/ace-step/ACE-Step.git@6ae0852b1388de6dc0cca26b31a86d711f723cb3",
    )
    .run_function(download_models, gpu="L4")
)


def build_prompt(genre: str, mood: str, energy: str) -> str:
    """Build a generation prompt from request parameters."""
    # Get BPM for this energy level
    bpm = ENERGY_BPM.get(energy, ENERGY_BPM["mid"])
    
    # Energy affects tempo and rhythm description
    energy_descriptions = {
        "low": f"{bpm} BPM, slow tempo, sparse arrangement",
        "mid": f"{bpm} BPM, moderate tempo, steady groove",
        "high": f"{bpm} BPM, upbeat tempo, driving rhythm"
    }
    
    # Mood affects the emotional tone
    mood_descriptions = {
        "happy": "uplifting, bright, positive",
        "sad": "melancholic, emotional, nostalgic",
        "calm": "peaceful, serene, relaxed",
        "exciting": "dynamic, engaging, energetic",
        "romantic": "warm, intimate, tender",
        "party": "fun, groovy, upbeat"
    }
    
    # Genre-specific instruments (limited to 2-3 for clarity)
    genre_instruments = {
        "pop": "electric piano, acoustic guitar",
        "rock": "clean electric guitar, organ",
        "hip_hop": "rhodes piano, vinyl samples",
        "jazz": "rhodes piano, upright bass",
        "classical": "grand piano, strings",
        "electronic": "analog synth, pad synth",
        "rnb": "rhodes piano, electric bass"
    }
    
    energy_desc = energy_descriptions.get(energy, energy_descriptions["mid"])
    mood_desc = mood_descriptions.get(mood, mood_descriptions["calm"])
    instruments = genre_instruments.get(genre, "rhodes piano, guitar")
    
    # Main lofi beat template with genre instruments plugged in
    prompt = (
        f"lofi hip hop instrumental, chillhop, {energy_desc}, "
        f"{mood_desc} mood, "
        f"featuring {instruments}, "
        "lofi drums with punchy kick and crisp snare, "
        "warm sub bass, "
        "clean mix, clear instrument separation, "
        "subtle tape warmth, vinyl texture, "
        "dry sound, minimal reverb, "
        "structured arrangement, "
        "no vocals, instrumental only, consistent tempo"
    )
    
    return prompt


@app.cls(
    image=image,
    gpu="L4",
    timeout=600,
)
class MusicGenerator:
    """GPU class for music generation with proper container lifecycle management."""
    
    @modal.enter()
    def load_model(self):
        """Load ACE-Step model once per container lifecycle."""
        from acestep.pipeline_ace_step import ACEStepPipeline
        
        self.pipeline = ACEStepPipeline(
            checkpoint_dir=CHECKPOINT_DIR,
            dtype="bfloat16",
            cpu_offload=False,
            overlapped_decode=True,
        )
        logger.info("ACE-Step model loaded successfully")
    
    @modal.method()
    def generate(self, genre: str, mood: str, energy: str) -> bytes:
        """
        Generate audio and return as bytes.
        
        Args:
            genre: Music genre (pop, rock, hip_hop, jazz, classical, electronic, rnb)
            mood: Mood (happy, sad, calm, exciting, romantic, party)
            energy: Energy level (low, mid, high)
        
        Returns:
            WAV audio data as bytes.
        """
        logger.info(f"Generating song: genre={genre}, mood={mood}, energy={energy}")
        
        generated_path = None
        
        try:
            # Build prompt (BPM is embedded in the prompt text)
            prompt = build_prompt(genre, mood, energy)
            
            generation_params = {
                "audio_duration": GENERATION_DURATION_SEC,
                "prompt": prompt,
                "lyrics": "[inst]",  # instrumental marker
                "format": "wav",
                # Inference settings - more steps for better quality
                "infer_step": 80,
                # Higher guidance scale for stronger prompt adherence (including BPM in text)
                "guidance_scale": 18,
                "scheduler_type": "euler",
                "cfg_type": "apg",
                # Higher omega scale for better prompt following
                "omega_scale": 12,
                # Guidance throughout the generation for consistency
                "guidance_interval": 0.7,
                "guidance_interval_decay": 0.1,
                "min_guidance_scale": 5,
                # ERG settings for better control
                "use_erg_tag": True,
                "use_erg_lyric": True,
                "use_erg_diffusion": True,
            }
            
            # Create temporary file for the generated audio
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".wav",
                prefix="generated_"
            )
            generated_path = Path(temp_file.name)
            temp_file.close()
            
            # Generate audio
            logger.info("Starting audio generation...")
            self.pipeline(**generation_params, save_path=str(generated_path))
            logger.info(f"Generated audio: {generated_path}")
            
            # Read and return audio bytes
            with open(generated_path, "rb") as f:
                audio_bytes = f.read()
            
            logger.info(f"Returning {len(audio_bytes)} bytes of audio data")
            return audio_bytes
            
        finally:
            # Cleanup temp file
            if generated_path and generated_path.exists():
                os.remove(generated_path)


@app.local_entrypoint()
def main(
    genre: str = "electronic",
    mood: str = "calm",
    energy: str = "mid",
    output: str = "output.wav"
):
    """
    Local entrypoint for testing.
    
    Usage:
        modal run app.py --genre electronic --mood calm --energy mid --output my_song.wav
    """
    logger.info(f"Generating: genre={genre}, mood={mood}, energy={energy}")
    
    generator = MusicGenerator()
    audio_bytes = generator.generate.remote(genre, mood, energy)
    
    # Save to local file
    with open(output, "wb") as f:
        f.write(audio_bytes)
    
    logger.info(f"Saved to {output} ({len(audio_bytes)} bytes)")
