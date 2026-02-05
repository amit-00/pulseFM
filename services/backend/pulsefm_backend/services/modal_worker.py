import modal
from pulsefm_models.request import RequestGenre, RequestMood, RequestEnergy


async def dispatch_to_modal_worker(
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
        genre=genre.value,
        mood=mood.value,
        energy=energy.value
    )
