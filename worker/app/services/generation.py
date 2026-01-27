"""Music generation service using ACE-Step model."""
import logging
import tempfile
from pathlib import Path
from typing import Optional

import torch
import soundfile as sf

from app.config.settings import (
    ACE_STEP_CHECKPOINT_PATH,
    GENERATION_DURATION_SEC,
    GENERATION_SEED,
)

logger = logging.getLogger(__name__)

# Global pipeline instance for model reuse
_pipeline = None


def get_pipeline():
    """Get or initialize the ACE-Step pipeline (singleton pattern)."""
    global _pipeline
    
    if _pipeline is None:
        logger.info("Loading ACE-Step model...")
        from acestep import ACEStepPipeline
        
        _pipeline = ACEStepPipeline.from_pretrained(
            ACE_STEP_CHECKPOINT_PATH,
            torch_dtype=torch.bfloat16,
        )
        _pipeline.to("cuda")
        logger.info("ACE-Step model loaded successfully")
    
    return _pipeline


def build_prompt(genre: str, mood: str, energy: str) -> str:
    """
    Build a generation prompt from request parameters.
    
    Constructs a descriptive prompt optimized for lofi instrumental generation
    while incorporating the user's genre, mood, and energy preferences.
    """
    # Energy level descriptions
    energy_descriptions = {
        "low": "slow tempo, relaxed, minimal beats",
        "mid": "moderate tempo, balanced rhythm, steady groove",
        "high": "upbeat tempo, energetic, driving rhythm"
    }
    
    # Mood descriptions
    mood_descriptions = {
        "happy": "uplifting, bright, positive vibes",
        "sad": "melancholic, emotional, nostalgic",
        "calm": "peaceful, serene, meditative",
        "exciting": "dynamic, thrilling, intense",
        "romantic": "warm, intimate, tender",
        "party": "fun, celebratory, lively"
    }
    
    # Genre style hints (all will be rendered as lofi versions)
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
    
    # Build the prompt - always instrumental lofi with user preferences
    prompt = (
        f"lofi hip hop instrumental, {genre_style}, "
        f"{mood_desc}, {energy_desc}, "
        "lo-fi beats, chillhop, study music, "
        "warm analog synths, soft drums, atmospheric pads, "
        "no vocals, instrumental only"
    )
    
    logger.debug(f"Built prompt: {prompt}")
    return prompt


def generate_song_request(
    genre: str,
    mood: str,
    energy: str,
    seed: Optional[int] = None
) -> Path:
    """
    Generate a song using ACE-Step model based on request parameters.
    
    Args:
        genre: Music genre (from RequestGenre enum)
        mood: Mood of the track (from RequestMood enum)
        energy: Energy level (from RequestEnergy enum)
        seed: Optional random seed for reproducibility
    
    Returns:
        Path to the generated .wav file (temporary file)
    
    Raises:
        RuntimeError: If generation fails
    """
    logger.info(f"Generating song: genre={genre}, mood={mood}, energy={energy}")
    
    try:
        pipeline = get_pipeline()
        
        # Build prompt from request parameters
        prompt = build_prompt(genre, mood, energy)
        
        # Use configured seed or provided seed
        generation_seed = seed if seed is not None else GENERATION_SEED
        
        # Generation parameters tuned for L4 GPU (24GB VRAM) and coherent output
        # These parameters reduce randomness while maintaining musical interest
        generation_params = {
            "prompt": prompt,
            "duration": GENERATION_DURATION_SEC,
            "instrumental": True,  # Always instrumental
            "num_inference_steps": 100,  # Balance quality/speed
            "guidance_scale": 7.5,  # Moderate prompt adherence
            "tag_guidance_scale": 3.0,  # Style consistency
            "min_guidance_scale": 2.0,  # Floor to prevent randomness
            "guidance_interval": 0.5,  # Smooth transitions
            "guidance_interval_decay": 0.0,  # Consistent guidance throughout
            "lyric_guidance_scale": 0.0,  # No lyrics for instrumental
        }
        
        # Add seed if specified for reproducibility
        if generation_seed is not None:
            generation_params["seed"] = generation_seed
            logger.debug(f"Using seed: {generation_seed}")
        
        logger.info(f"Starting ACE-Step generation with {GENERATION_DURATION_SEC}s duration")
        
        # Generate audio
        result = pipeline(**generation_params)
        
        # Extract audio data from result
        # ACE-Step returns audio as numpy array with sample rate
        audio_data = result["audio"]
        sample_rate = result.get("sample_rate", 44100)
        
        # Create temporary file for the generated audio
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".wav",
            prefix="generated_"
        )
        output_path = Path(temp_file.name)
        temp_file.close()
        
        # Save audio to WAV file
        sf.write(str(output_path), audio_data, sample_rate)
        
        logger.info(f"Generated audio saved to: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Failed to generate song: {e}", exc_info=True)
        raise RuntimeError(f"Music generation failed: {str(e)}")


def unload_model():
    """Unload the model to free GPU memory."""
    global _pipeline
    
    if _pipeline is not None:
        logger.info("Unloading ACE-Step model...")
        del _pipeline
        _pipeline = None
        
        # Clear CUDA cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info("ACE-Step model unloaded")

