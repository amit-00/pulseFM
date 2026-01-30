"""Modal worker for PulseFM music generation."""
import logging
import modal
import shutil
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
BUCKET_NAME = "pulsefm-generated-music"  # Replace with your actual bucket name
CHECKPOINT_DIR = "/checkpoints/ACE-Step/ACE-Step-v1-3.5B"
GENERATION_DURATION_SEC = 90

app = modal.App("pulsefm-worker")


def download_models():
    """Download ACE-Step models during image build."""
    from huggingface_hub import snapshot_download
    
    snapshot_download(
        repo_id="ACE-Step/ACE-Step-v1-3.5B",
        local_dir="/checkpoints/ACE-Step/ACE-Step-v1-3.5B"
    )


# Build image with CUDA, ffmpeg, and ACE-Step
image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04",
        add_python="3.11"
    )
    .apt_install("ffmpeg", "libsndfile1", "git")
    .pip_install(
        "torch",
        "torchaudio",
        extra_index_url="https://download.pytorch.org/whl/cu121"
    )
    .pip_install("soundfile", "huggingface-hub")
    .run_commands("pip install git+https://github.com/ace-step/ACE-Step.git")
    .run_function(download_models, gpu="L4")
)

# GCS bucket mount for output files
gcs_bucket = modal.CloudBucketMount(
    bucket_name=BUCKET_NAME,
    secret=modal.Secret.from_name("gcs-credentials")
)


@app.cls(image=image, gpu="L4", volumes={"/gcs": gcs_bucket}, timeout=600)
class Generator:
    """Music generation worker using ACE-Step model."""
    
    @modal.enter()
    def load_model(self):
        """Initialize ACE-Step pipeline once per container."""
        from acestep.pipeline_ace_step import ACEStepPipeline
        
        self.pipeline = ACEStepPipeline(
            checkpoint_dir=CHECKPOINT_DIR,
            dtype="bfloat16",
            torch_compile=True,
        )
        logger.info("ACE-Step model loaded successfully")
    
    def _build_prompt(self, genre: str, mood: str, energy: str) -> str:
        """Build a generation prompt from request parameters."""
        energy_descriptions = {
            "low": "slow tempo, relaxed, minimal beats",
            "mid": "moderate tempo, balanced rhythm, steady groove",
            "high": "upbeat tempo, energetic, driving rhythm"
        }
        
        mood_descriptions = {
            "happy": "uplifting, bright, positive vibes",
            "sad": "melancholic, emotional, nostalgic",
            "calm": "peaceful, serene, meditative",
            "exciting": "dynamic, thrilling, intense",
            "romantic": "warm, intimate, tender",
            "party": "fun, celebratory, lively"
        }
        
        genre_styles = {
            "pop": "catchy melodies, polished sound",
            "rock": "guitar-driven, raw energy",
            "hip_hop": "boom bap beats, urban vibes",
            "jazz": "sophisticated harmonies, smooth progressions",
            "classical": "orchestral elements, elegant composition",
            "electronic": "synth textures, digital soundscapes",
            "rnb": "soulful grooves, smooth melodies"
        }
        
        energy_desc = energy_descriptions.get(energy, energy_descriptions["mid"])
        mood_desc = mood_descriptions.get(mood, mood_descriptions["calm"])
        genre_style = genre_styles.get(genre, "warm analog feel, vinyl crackle")
        
        prompt = (
            f"lofi hip hop instrumental, {genre_style}, "
            f"{mood_desc}, {energy_desc}, "
            "lo-fi beats, chillhop, study music, "
            "warm analog synths, soft drums, atmospheric pads, "
            "no vocals, instrumental only"
        )
        
        return prompt
    
    def _generate_audio(self, genre: str, mood: str, energy: str) -> Path:
        """Generate audio using ACE-Step model."""
        prompt = self._build_prompt(genre, mood, energy)
        
        generation_params = {
            "prompt": prompt,
            "duration": GENERATION_DURATION_SEC,
            "instrumental": True,
            "num_inference_steps": 100,
            "guidance_scale": 7.5,
            "tag_guidance_scale": 3.0,
            "min_guidance_scale": 2.0,
            "guidance_interval": 0.5,
            "guidance_interval_decay": 0.0,
            "lyric_guidance_scale": 0.0,
        }
        
        # Create temporary file for the generated audio
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".wav",
            prefix="generated_"
        )
        output_path = Path(temp_file.name)
        temp_file.close()
        
        # Generate audio
        self.pipeline(**generation_params, save_path=output_path)
        
        return output_path
    
    @modal.method()
    def generate(
        self,
        request_id: str,
        genre: str,
        mood: str,
        energy: str
    ) -> dict:
        """
        Generate a song and upload to GCS.
        
        Args:
            request_id: Unique identifier for the request
            genre: Music genre (pop, rock, hip_hop, jazz, classical, electronic, rnb)
            mood: Mood of the track (happy, sad, calm, exciting, romantic, party)
            energy: Energy level (low, mid, high)
        
        Returns:
            dict with audio_url
        """
        import os
        
        logger.info(f"Generating song: request_id={request_id}, genre={genre}, mood={mood}, energy={energy}")
        
        generated_path = None
        
        try:
            # Step 1: Generate audio
            logger.info("Starting audio generation...")
            generated_path = self._generate_audio(genre, mood, energy)
            logger.debug(f"Generated audio: {generated_path}")
            
            # Step 2: Write raw wav to GCS via CloudBucketMount
            gcs_output_path = Path(f"/gcs/raw/{request_id}.wav")
            gcs_output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Writing to GCS: {gcs_output_path}")
            shutil.copy(generated_path, gcs_output_path)
            
            audio_url = f"gs://{BUCKET_NAME}/raw/{request_id}.wav"
            logger.info(f"Successfully uploaded: {audio_url}")
            
            return {"audio_url": audio_url}
            
        finally:
            # Cleanup temp file
            if generated_path and generated_path.exists():
                os.remove(generated_path)


@app.local_entrypoint()
def main(
    request_id: str,
    genre: str = "electronic",
    mood: str = "calm",
    energy: str = "mid"
):
    """Local entrypoint for testing."""
    generator = Generator()
    result = generator.generate.remote(
        request_id=request_id,
        genre=genre,
        mood=mood,
        energy=energy
    )
    logger.info(f"Result: {result}")

