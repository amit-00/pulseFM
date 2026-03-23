"""Modal worker for PulseFM music generation."""

from __future__ import annotations

import logging
import os
import random
import secrets
import tempfile
import time
import uuid
from pathlib import Path

import modal
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CHECKPOINT_DIR = "/checkpoints/ACE-Step/ACE-Step-v1-3.5B"
GENERATION_DURATION_SEC = 150
ACE_STEP_MAX_SEED = 2_147_483_647
ENCODED_CACHE_CONTROL = "public,max-age=300,s-maxage=3600"

USE_GPU_SNAPSHOT = True

ENERGY_BPM = {
    "low": 70,
    "mid": 85,
    "high": 100,
}

app = modal.App("pulsefm-worker")
runtime_secret = modal.Secret.from_name("pulsefm-modal-runtime")


def download_models():
    """Download ACE-Step models during image build."""
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id="ACE-Step/ACE-Step-v1-3.5B",
        local_dir=CHECKPOINT_DIR,
    )


image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "torch==2.8.0",
        "torchaudio==2.8.0",
        "boto3",
        "huggingface-hub",
        "pydub",
        "requests",
        "soundfile",
        "git+https://github.com/ace-step/ACE-Step.git@6ae0852b1388de6dc0cca26b31a86d711f723cb3",
    )
    .env(
        {
            "XFORMERS_ENABLE_TRITON": "1",
            "TORCHDYNAMO_DISABLE": "1",
        }
    )
    .run_function(download_models, gpu="L4")
)

web_image = modal.Image.debian_slim(python_version="3.12").pip_install("fastapi", "pydantic")


class DescriptorPayload(BaseModel):
    genre: str = Field(min_length=1)
    mood: str = Field(min_length=1)
    energy: str = Field(min_length=1)


class GenerationJobRequest(BaseModel):
    voteId: str = Field(min_length=1)
    workflowInstanceId: str = Field(min_length=1)
    descriptor: DescriptorPayload
    callbackUrl: str = Field(min_length=1)
    callbackSecret: str = Field(min_length=1)
    outputKey: str = Field(min_length=1)
    winnerOption: str | None = None


def build_prompt(genre: str, mood: str, energy: str) -> str:
    """Build a generation prompt from request parameters."""
    bpm = ENERGY_BPM.get(energy, ENERGY_BPM["mid"])

    energy_descriptions = {
        "low": f"{bpm} BPM, slow tempo, sparse arrangement",
        "mid": f"{bpm} BPM, moderate tempo, steady groove",
        "high": f"{bpm} BPM, upbeat tempo, driving rhythm",
    }

    mood_descriptions = {
        "happy": "uplifting, bright, positive, major key, cheerful melody",
        "sad": "melancholic, somber, minor key, bittersweet, introspective, mournful undertones, emotional depth",
        "calm": "peaceful, serene, relaxed, ambient, gentle, soft dynamics",
        "exciting": "dynamic, energetic, building tension, powerful, intense",
        "romantic": "warm, intimate, tender, dreamy, lush harmonies",
        "party": "fun, groovy, danceable, infectious rhythm, high energy",
    }

    genre_instruments = {
        "pop": "electric piano, acoustic guitar",
        "rock": "clean electric guitar, organ",
        "hip_hop": "rhodes piano, vinyl samples",
        "jazz": "rhodes piano, upright bass",
        "electronic": "analog synth, pad synth",
        "rnb": "rhodes piano, electric bass",
    }

    energy_desc = energy_descriptions.get(energy, energy_descriptions["mid"])
    mood_desc = mood_descriptions.get(mood, mood_descriptions["calm"])
    instruments = genre_instruments.get(genre, "rhodes piano, guitar")

    return (
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


def _next_seed() -> int:
    return secrets.randbelow(ACE_STEP_MAX_SEED + 1)


def _apply_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        logger.warning("Failed to apply torch seed", extra={"seed": seed})


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _normalize_output_key(output_key: str) -> str:
    normalized = output_key.lstrip("/")
    if not normalized.endswith(".m4a"):
        raise ValueError("outputKey must end with .m4a")
    return normalized


def _join_url(base: str, key: str) -> str:
    return f"{base.rstrip('/')}/{key.lstrip('/')}"


def _build_job_id(vote_id: str) -> str:
    return f"{vote_id}-{uuid.uuid4().hex}"


web_app = FastAPI(title="PulseFM Modal Generator", version="1.0.0")


def _authorize(authorization: str | None) -> None:
    expected = _require_env("MODAL_WEBHOOK_TOKEN")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@web_app.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(job: GenerationJobRequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    _authorize(authorization)
    output_key = _normalize_output_key(job.outputKey)
    external_job_id = _build_job_id(job.voteId)

    MusicGenerator().generate.spawn(
        genre=job.descriptor.genre,
        mood=job.descriptor.mood,
        energy=job.descriptor.energy,
        vote_id=job.voteId,
        workflow_instance_id=job.workflowInstanceId,
        callback_url=job.callbackUrl,
        callback_secret=job.callbackSecret,
        output_key=output_key,
        external_job_id=external_job_id,
        winner_option=job.winnerOption,
    )

    logger.info("Queued generation job", extra={"vote_id": job.voteId, "external_job_id": external_job_id})
    return {"jobId": external_job_id}


@app.function(image=web_image, secrets=[runtime_secret])
@modal.asgi_app()
def api():
    return web_app


@app.cls(
    image=image,
    cpu=4,
    memory=16384,
    gpu="L4",
    min_containers=0,
    timeout=900,
    secrets=[runtime_secret],
    scaledown_window=2,
    enable_memory_snapshot=True,
    experimental_options=({"enable_gpu_snapshot": True} if USE_GPU_SNAPSHOT else {}),
)
class MusicGenerator:
    """GPU class for music generation with memory snapshot support."""

    @modal.enter(snap=True)
    def snapshot_load(self):
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
        t_total = time.monotonic()
        logger.info("enter(snap=False) starting")

        if not USE_GPU_SNAPSHOT:
            import torch

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
        self._init_storage()
        logger.info(
            "enter(snap=False) complete in %.1fs [model_ready=%s]",
            time.monotonic() - t_total,
            self._model_ready,
        )

    def _init_storage(self) -> None:
        import boto3

        self.r2_client = boto3.client(
            "s3",
            endpoint_url=_require_env("R2_ENDPOINT_URL"),
            aws_access_key_id=_require_env("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=_require_env("R2_SECRET_ACCESS_KEY"),
            region_name=os.getenv("R2_REGION", "auto"),
        )
        self.r2_bucket = _require_env("R2_BUCKET_NAME")
        self.public_audio_base_url = _require_env("PUBLIC_AUDIO_BASE_URL").rstrip("/")
        self.encoded_cache_control = os.getenv("ENCODED_CACHE_CONTROL", ENCODED_CACHE_CONTROL)
        self.callback_timeout_sec = float(os.getenv("CALLBACK_TIMEOUT_SEC", "15"))
        logger.info("R2 client initialized for bucket: %s", self.r2_bucket)

    def _encode_audio(self, source_path: Path, output_path: Path) -> int:
        from pydub import AudioSegment

        audio = AudioSegment.from_wav(str(source_path))
        duration_ms = len(audio)
        audio.export(
            str(output_path),
            format="ipod",
            codec="aac",
            bitrate="128k",
            parameters=["-ar", "48000"],
        )
        return duration_ms

    def _upload_encoded(self, output_path: Path, output_key: str) -> str:
        self.r2_client.upload_file(
            str(output_path),
            self.r2_bucket,
            output_key,
            ExtraArgs={
                "ContentType": "audio/mp4",
                "CacheControl": self.encoded_cache_control,
            },
        )
        public_url = _join_url(self.public_audio_base_url, output_key)
        logger.info("Uploaded encoded audio to %s", public_url)
        return public_url

    def _notify_ready(
        self,
        *,
        vote_id: str,
        workflow_instance_id: str,
        callback_url: str,
        callback_secret: str,
        external_job_id: str,
        duration_ms: int,
        output_key: str,
        public_url: str,
        winner_option: str | None,
    ) -> None:
        import requests

        payload = {
            "voteId": vote_id,
            "workflowInstanceId": workflow_instance_id,
            "externalJobId": external_job_id,
            "durationMs": duration_ms,
            "r2Key": output_key,
            "publicUrl": public_url,
            "winnerOption": winner_option,
        }
        response = requests.post(
            callback_url,
            json=payload,
            headers={"X-Callback-Secret": callback_secret},
            timeout=self.callback_timeout_sec,
        )
        response.raise_for_status()
        logger.info("Posted generation callback for vote_id=%s", vote_id)

    @modal.method()
    def generate(
        self,
        *,
        genre: str,
        mood: str,
        energy: str,
        vote_id: str,
        workflow_instance_id: str,
        callback_url: str,
        callback_secret: str,
        output_key: str,
        external_job_id: str,
        winner_option: str | None = None,
    ) -> dict[str, str | int | None]:
        if not getattr(self, "_model_ready", False):
            raise RuntimeError("Model not ready -- snapshot restore may have failed.")

        output_key = _normalize_output_key(output_key)
        if not genre or not mood or not energy or not vote_id:
            raise ValueError("genre, mood, energy, and vote_id are required")

        t_start = time.monotonic()
        logger.info(
            "generate() start vote_id=%s genre=%s mood=%s energy=%s",
            vote_id,
            genre,
            mood,
            energy,
        )

        prompt = build_prompt(genre, mood, energy)
        seed = _next_seed()
        logger.info("Using generation seed for vote_id=%s seed=%d", vote_id, seed)

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

        with tempfile.TemporaryDirectory() as temp_dir:
            generated_path = Path(temp_dir) / f"{vote_id}.wav"
            encoded_path = Path(temp_dir) / Path(output_key).name

            t0 = time.monotonic()
            _apply_seed(seed)
            self.pipeline(**generation_params, save_path=str(generated_path))
            logger.info("Audio generated in %.1fs: %s", time.monotonic() - t0, generated_path)

            duration_ms = self._encode_audio(generated_path, encoded_path)
            public_url = self._upload_encoded(encoded_path, output_key)
            self._notify_ready(
                vote_id=vote_id,
                workflow_instance_id=workflow_instance_id,
                callback_url=callback_url,
                callback_secret=callback_secret,
                external_job_id=external_job_id,
                duration_ms=duration_ms,
                output_key=output_key,
                public_url=public_url,
                winner_option=winner_option,
            )

        elapsed = time.monotonic() - t_start
        logger.info("generate() complete in %.1fs for vote_id=%s", elapsed, vote_id)
        return {
            "voteId": vote_id,
            "externalJobId": external_job_id,
            "durationMs": duration_ms,
            "publicUrl": public_url,
        }

    @modal.method()
    def smoke_test(self) -> dict[str, object]:
        if not getattr(self, "_model_ready", False):
            return {"status": "error", "message": "Model not ready", "gpu_snapshot": USE_GPU_SNAPSHOT}

        t0 = time.monotonic()
        smoke_path = None
        try:
            seed = _next_seed()
            logger.info("Using smoke test seed=%d", seed)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav", prefix="smoke_")
            smoke_path = Path(temp_file.name)
            temp_file.close()

            _apply_seed(seed)
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
    callback_url = _require_env("LOCAL_CALLBACK_URL")
    callback_secret = _require_env("LOCAL_CALLBACK_SECRET")
    output_key = f"encoded/{vote_id}.m4a"
    external_job_id = _build_job_id(vote_id)

    logger.info("Generating: vote_id=%s output_key=%s", vote_id, output_key)
    MusicGenerator().generate.remote(
        genre=genre,
        mood=mood,
        energy=energy,
        vote_id=vote_id,
        workflow_instance_id=f"local-{vote_id}",
        callback_url=callback_url,
        callback_secret=callback_secret,
        output_key=output_key,
        external_job_id=external_job_id,
    )
    logger.info("Generation complete - encoded audio uploaded to R2")
