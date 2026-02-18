import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("PROJECT_ID", "")
    stations_collection: str = os.getenv("STATIONS_COLLECTION", "stations")
    songs_collection: str = os.getenv("SONGS_COLLECTION", "songs")
    vote_state_collection: str = os.getenv("VOTE_STATE_COLLECTION", "voteState")
    playback_queue: str = os.getenv("PLAYBACK_QUEUE_NAME", "playback-queue")
    playback_tick_url: str = os.getenv("PLAYBACK_TICK_URL", "")
    playback_events_topic: str = os.getenv("PLAYBACK_EVENTS_TOPIC", "playback")
    vote_events_topic: str = os.getenv("VOTE_EVENTS_TOPIC", "vote-events")
    window_seconds: int = int(os.getenv("WINDOW_SECONDS", "300"))
    options_per_window: int = int(os.getenv("OPTIONS_PER_WINDOW", "4"))
    vote_options: list[str] = field(default_factory=lambda: [opt.strip() for opt in os.getenv("VOTE_OPTIONS", "").split(",") if opt.strip()])


settings = Settings()
