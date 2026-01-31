import os
import modal
from app.models.request import RequestGenre, RequestMood, RequestEnergy


async def dispatch_to_modal_worker(
    request_id: str,
    genre: RequestGenre,
    mood: RequestMood,
    energy: RequestEnergy
):
    """
    Dispatch a request to Modal
    """
    
    # Look up the remote MusicGenerator class
    MusicGenerator = modal.Cls.from_name("pulsefm-worker", "MusicGenerator")
    
    # Instantiate the class
    generator = MusicGenerator()
    
    await generator.generate.spawn.aio(
        request_id=request_id,
        genre=genre.value,
        mood=mood.value,
        energy=energy.value
    )

