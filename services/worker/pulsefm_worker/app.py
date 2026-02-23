"""Modal worker for PulseFM music generation."""
import json
import logging
import modal
import tempfile
import time
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
CHECKPOINT_DIR = "/checkpoints/ACE-Step/ACE-Step-v1-3.5B"
GENERATION_DURATION_SEC = 150
GCS_BUCKET_NAME = "pulsefm-generated-songs"

# Snapshot mode toggle (evaluated at deploy time on the local machine).
# Set False to fall back to CPU snapshot + GPU load on startup.
USE_GPU_SNAPSHOT = True

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


image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "torch==2.8.0",
        "torchaudio==2.8.0",
        "huggingface-hub",
        "google-cloud-storage",
        "git+https://github.com/ace-step/ACE-Step.git@6ae0852b1388de6dc0cca26b31a86d711f723cb3",
    )
    .env({
        "XFORMERS_ENABLE_TRITON": "1",
        "TORCHDYNAMO_DISABLE": "1",
    })
    .run_function(download_models, gpu="L4")
)


def build_prompt(genre: str, mood: str, energy: str) -> str:
    """Build a generation prompt from request parameters."""
    bpm = ENERGY_BPM.get(energy, ENERGY_BPM["mid"])

    energy_descriptions = {
        "low": f"{bpm} BPM, slow tempo, sparse arrangement",
        "mid": f"{bpm} BPM, moderate tempo, steady groove",
        "high": f"{bpm} BPM, upbeat tempo, driving rhythm"
    }

    mood_descriptions = {
        "happy": "uplifting, bright, positive, major key, cheerful melody",
        "sad": "melancholic, somber, minor key, bittersweet, introspective, mournful undertones, emotional depth",
        "calm": "peaceful, serene, relaxed, ambient, gentle, soft dynamics",
        "exciting": "dynamic, energetic, building tension, powerful, intense",
        "romantic": "warm, intimate, tender, dreamy, lush harmonies",
        "party": "fun, groovy, danceable, infectious rhythm, high energy"
    }

    genre_instruments = {
        "pop": "electric piano, acoustic guitar",
        "rock": "clean electric guitar, organ",
        "hip_hop": "rhodes piano, vinyl samples",
        "jazz": "rhodes piano, upright bass",
        "electronic": "analog synth, pad synth",
        "rnb": "rhodes piano, electric bass"
    }

    energy_desc = energy_descriptions.get(energy, energy_descriptions["mid"])
    mood_desc = mood_descriptions.get(mood, mood_descriptions["calm"])
    instruments = genre_instruments.get(genre, "rhodes piano, guitar")

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
    cpu=4,
    memory=16384,
    gpu="L4",
    timeout=600,
    secrets=[gcs_secret],
    scaledown_window=2,
    enable_memory_snapshot=True,
    experimental_options=({"enable_gpu_snapshot": True} if USE_GPU_SNAPSHOT else {}),
)
class MusicGenerator:
    """GPU class for music generation with memory snapshot support."""

    @modal.enter(snap=True)
    def snapshot_load(self):
        """Load ACE-Step model into the memory snapshot.

        GPU mode:  model goes directly to GPU; snapshot captures GPU memory.
        CPU mode:  model stays on CPU; moved to GPU in post_restore().
        """
        t_total = time.monotonic()
        mode = "GPU" if USE_GPU_SNAPSHOT else "CPU"
        logger.info("enter(snap=True) starting [%s snapshot mode]", mode)

        t0 = time.monotonic()
        logger.info("Importing ACE-Step pipeline...")
        from acestep.pipeline_ace_step import ACEStepPipeline
        logger.info("ACE-Step imported in %.1fs", time.monotonic() - t0)

        t0 = time.monotonic()
        logger.info("Loading ACE-Step v1-3.5B model (device=%s)...", mode.lower())
        self.pipeline = ACEStepPipeline(
            checkpoint_dir=CHECKPOINT_DIR,
            dtype="bfloat16",
            cpu_offload=not USE_GPU_SNAPSHOT,
            overlapped_decode=True,
        )
        logger.info("Model loaded in %.1fs", time.monotonic() - t0)

        self._model_ready = USE_GPU_SNAPSHOT
        logger.info(
            "enter(snap=True) complete in %.1fs [model_ready=%s]",
            time.monotonic() - t_total,
            self._model_ready,
        )

    @modal.enter(snap=False)
    def post_restore(self):
        """Post-restore: move model to GPU (CPU mode) and init GCS client."""
        t_total = time.monotonic()
        logger.info("enter(snap=False) starting")

        if not USE_GPU_SNAPSHOT:
            import torch  # re-import to reinitialize CUDA state after restore
            logger.info("CUDA available: %s", torch.cuda.is_available())

            t0 = time.monotonic()
            logger.info("Moving model to GPU...")
            self.pipeline.cpu_offload = False
            if hasattr(self.pipeline, "to"):
                self.pipeline.to("cuda")
            elif hasattr(self.pipeline, "model") and hasattr(self.pipeline.model, "to"):
                self.pipeline.model.to("cuda")
            logger.info("Model moved to GPU in %.1fs", time.monotonic() - t0)

        self._model_ready = True
        self._init_gcs()
        logger.info(
            "enter(snap=False) complete in %.1fs [model_ready=%s]",
            time.monotonic() - t_total,
            self._model_ready,
        )

    def _init_gcs(self):
        """Initialize Google Cloud Storage client from Modal secret."""
        from google.cloud import storage
        from google.oauth2 import service_account

        credentials_json = os.environ.get("GCS_CREDENTIALS_JSON")
        if not credentials_json:
            raise ValueError(
                "GCS_CREDENTIALS_JSON environment variable is not set. "
                "Create the secret with: modal secret create gcs-credentials GCS_CREDENTIALS_JSON=@pulsefm-worker-key.json"
            )

        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)

        self.gcs_client = storage.Client(credentials=credentials, project=credentials_info["project_id"])
        self.bucket = self.gcs_client.bucket(GCS_BUCKET_NAME)
        logger.info("GCS client initialized for bucket: %s", GCS_BUCKET_NAME)

    @modal.method()
    def generate(self, genre: str, mood: str, energy: str, vote_id: str) -> None:
        """
        Generate audio and upload to GCS bucket.

        Args:
            genre: Musical genre
            mood: Musical mood
            energy: Energy level
            vote_id: Vote identifier used for naming the output file
        """
        if not getattr(self, "_model_ready", False):
            raise RuntimeError(
                "Model not ready -- snapshot restore may have failed. "
                "Check enter() logs for errors."
            )

        t_start = time.monotonic()
        logger.info("generate() start: vote_id=%s genre=%s mood=%s energy=%s", vote_id, genre, mood, energy)

        if not genre or not mood or not energy:
            logger.error("Missing genre/mood/energy for vote %s. Ending execution.", vote_id)
            return
        if not vote_id:
            logger.error("Missing vote_id. Ending execution.")
            return

        generated_path = None

        try:
            prompt = build_prompt(genre, mood, energy)

            generation_params = {
                "audio_duration": GENERATION_DURATION_SEC,
                "prompt": prompt,
                "lyrics": "[instrumental]",
                "format": "wav",
                "infer_step": 40,
                "guidance_scale": 18,
                "scheduler_type": "euler",
                "cfg_type": "apg",
                "omega_scale": 12,
                "guidance_interval": 0.7,
                "guidance_interval_decay": 0.1,
                "min_guidance_scale": 5,
                "use_erg_tag": True,
                "use_erg_lyric": True,
                "use_erg_diffusion": True,
            }

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".wav",
                prefix="generated_"
            )
            generated_path = Path(temp_file.name)
            temp_file.close()

            logger.info("Starting audio generation...")
            t0 = time.monotonic()
            self.pipeline(**generation_params, save_path=str(generated_path))
            logger.info("Audio generated in %.1fs: %s", time.monotonic() - t0, generated_path)

            blob_name = f"raw/{vote_id}.wav"
            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(str(generated_path), content_type="audio/wav")

            blob.reload()
            gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_name}"
            logger.info("Uploaded to GCS: %s (size: %s bytes)", gcs_uri, blob.size)

        except Exception:
            logger.exception("generate() failed for vote_id=%s", vote_id)
            raise

        finally:
            if generated_path and generated_path.exists():
                os.remove(generated_path)

        logger.info("generate() complete in %.1fs: vote_id=%s", time.monotonic() - t_start, vote_id)

    @modal.method()
    def smoke_test(self) -> dict:
        """Quick generation to verify snapshot restore and inference work."""
        if not getattr(self, "_model_ready", False):
            return {"status": "error", "message": "Model not ready", "gpu_snapshot": USE_GPU_SNAPSHOT}

        t0 = time.monotonic()
        smoke_path = None
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav", prefix="smoke_")
            smoke_path = Path(temp_file.name)
            temp_file.close()

            self.pipeline(
                audio_duration=10,
                prompt="lofi hip hop instrumental, calm, test",
                lyrics="[instrumental]",
                infer_step=2,
                guidance_scale=1.0,
                save_path=str(smoke_path),
            )

            audio_bytes = smoke_path.stat().st_size
            elapsed = time.monotonic() - t0
            logger.info("smoke_test passed in %.1fs (%d bytes)", elapsed, audio_bytes)
            return {
                "status": "ok",
                "duration_sec": round(elapsed, 2),
                "audio_bytes": audio_bytes,
                "gpu_snapshot": USE_GPU_SNAPSHOT,
            }

        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.exception("smoke_test failed after %.1fs", elapsed)
            return {
                "status": "error",
                "message": str(exc),
                "duration_sec": round(elapsed, 2),
                "gpu_snapshot": USE_GPU_SNAPSHOT,
            }

        finally:
            if smoke_path and smoke_path.exists():
                os.remove(smoke_path)


@app.local_entrypoint()
def main(genre: str = "pop", mood: str = "calm", energy: str = "mid", vote_id: str = "vote-test"):
    """
    Local entrypoint for testing.

    Usage:
        modal run pulsefm_worker/app.py --genre pop --mood calm --energy mid --vote-id vote-1

    The generated audio will be uploaded to the GCS bucket.
    """
    logger.info(f"Generating: vote_id={vote_id}")

    generator = MusicGenerator()
    generator.generate.remote(genre=genre, mood=mood, energy=energy, vote_id=vote_id)

    logger.info("Generation complete - audio uploaded to GCS")
