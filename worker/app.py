"""Modal worker for PulseFM music generation."""
import json
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
GCS_BUCKET_NAME = "pulsefm-generated-songs"

# BPM settings for each energy level - keeps tempo consistent
ENERGY_BPM = {
    "low": 70,    # Slow, dreamy lofi
    "mid": 85,    # Classic study beats tempo
    "high": 100,  # Upbeat but still lofi
}

app = modal.App("pulsefm-worker")

# Reference GCS credentials stored in Modal secret
# Create with: modal secret create gcs-credentials GCS_CREDENTIALS_JSON=@pulsefm-worker-key.json
gcs_secret = modal.Secret.from_name("gcs-credentials")


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
        "google-cloud-storage",
        "google-cloud-firestore",
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
    
    # Mood affects the emotional tone - be specific about musical qualities
    mood_descriptions = {
        "happy": "uplifting, bright, positive, major key, cheerful melody",
        "sad": "melancholic, somber, minor key, bittersweet, introspective, mournful undertones, emotional depth",
        "calm": "peaceful, serene, relaxed, ambient, gentle, soft dynamics",
        "exciting": "dynamic, energetic, building tension, powerful, intense",
        "romantic": "warm, intimate, tender, dreamy, lush harmonies",
        "party": "fun, groovy, danceable, infectious rhythm, high energy"
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
    secrets=[gcs_secret],
)
class MusicGenerator:
    """GPU class for music generation with proper container lifecycle management."""
    
    @modal.enter()
    def load_model(self):
        """Load ACE-Step model once per container lifecycle."""
        from acestep.pipeline_ace_step import ACEStepPipeline
        from google.cloud import storage, firestore
        from google.oauth2 import service_account
        
        self.pipeline = ACEStepPipeline(
            checkpoint_dir=CHECKPOINT_DIR,
            dtype="bfloat16",
            cpu_offload=False,
            overlapped_decode=True,
        )
        logger.info("ACE-Step model loaded successfully")
        
        # Initialize GCS client from credentials
        credentials_json = os.environ.get("GCS_CREDENTIALS_JSON")
        if not credentials_json:
            raise ValueError(
                "GCS_CREDENTIALS_JSON environment variable is not set. "
                "Create the secret with: modal secret create gcs-credentials GCS_CREDENTIALS_JSON=@pulsefm-worker-key.json"
            )

        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)

        # Initialize GCS client
        self.gcs_client = storage.Client(credentials=credentials, project=credentials_info["project_id"])
        self.bucket = self.gcs_client.bucket(GCS_BUCKET_NAME)
        logger.info(f"GCS client initialized for bucket: {GCS_BUCKET_NAME}")
        
        # Initialize Firestore client using same credentials
        self.firestore_client = firestore.Client(credentials=credentials, project=credentials_info["project_id"])
        self.requests_collection = self.firestore_client.collection("requests")
        logger.info("Firestore client initialized for 'requests' collection")
    
    @modal.method()
    def generate(self, request_id: str) -> None:
        """
        Generate audio and upload to GCS bucket.
        
        Args:
            request_id: Unique request identifier (used as filename and document ID)
        """
        logger.info(f"Generating song: request_id={request_id}")
        
        # Check if document exists in Firestore and get its data
        doc_ref = self.requests_collection.document(request_id)
        try:
            doc = doc_ref.get()
            if not doc.exists:
                logger.error(f"Document with request_id '{request_id}' does not exist in Firestore. Ending execution.")
                return
            
            # Read genre, mood, and energy from the document
            doc_data = doc.to_dict()
            genre = doc_data.get("genre")
            mood = doc_data.get("mood")
            energy = doc_data.get("energy")
            
            # Validate required fields
            if not genre:
                logger.error(f"Document {request_id} is missing 'genre' field. Ending execution.")
                return
            if not mood:
                logger.error(f"Document {request_id} is missing 'mood' field. Ending execution.")
                return
            if not energy:
                logger.error(f"Document {request_id} is missing 'energy' field. Ending execution.")
                return
            
            logger.info(f"Read parameters from Firestore: genre={genre}, mood={mood}, energy={energy}")
            
        except Exception as e:
            logger.error(f"Error reading Firestore document: {e}. Ending execution.")
            return
        
        # Update status to "generating"
        try:
            doc_ref.update({"status": "generating"})
            logger.info(f"Updated Firestore document {request_id} status to 'generating'")
        except Exception as e:
            logger.warning(f"Error updating Firestore status to 'generating': {e}. Continuing with generation.")
        
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
            
            # Upload to GCS
            blob_name = f"raw/{request_id}.wav"
            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(str(generated_path), content_type="audio/wav")
            
            # Verify upload succeeded
            blob.reload()
            gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_name}"
            logger.info(f"Uploaded audio to GCS: {gcs_uri} (size: {blob.size} bytes)")
            
            # Update Firestore document with status "ready" and audio_url
            try:
                doc_ref.update({
                    "status": "ready",
                    "audio_url": gcs_uri
                })
                logger.info(f"Updated Firestore document {request_id} status to 'ready' with audio_url: {gcs_uri}")
            except Exception as e:
                logger.warning(f"Error updating Firestore status to 'ready': {e}")
            
        finally:
            # Cleanup temp file
            if generated_path and generated_path.exists():
                os.remove(generated_path)


@app.local_entrypoint()
def main(request_id: str = "test"):
    """
    Local entrypoint for testing.
    
    Usage:
        modal run app.py --request-id my-song
    
    The generated audio will be uploaded to the GCS bucket.
    Genre, mood, and energy are read from the Firestore document.
    """
    logger.info(f"Generating: request_id={request_id}")
    
    generator = MusicGenerator()
    generator.generate.remote(request_id)
    
    logger.info("Generation complete - audio uploaded to GCS")
