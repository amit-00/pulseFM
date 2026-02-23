import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    modal_queue_name: str = os.getenv("MODAL_QUEUE_NAME", "playback-queue")
    modal_dispatch_service_url: str = os.getenv("MODAL_DISPATCH_SERVICE_URL", "")
    warmup_lead_seconds: int = int(os.getenv("WARMUP_LEAD_SECONDS", "30"))
    scale_down_retry_horizon_seconds: int = int(os.getenv("SCALE_DOWN_RETRY_HORIZON_SECONDS", "300"))
    scale_down_retry_delay_seconds: int = int(os.getenv("SCALE_DOWN_RETRY_DELAY_SECONDS", "5"))

    heartbeat_active_key: str = os.getenv("HEARTBEAT_ACTIVE_KEY", "pulsefm:heartbeat:active")
    close_done_ttl_seconds: int = int(os.getenv("CLOSE_DONE_TTL_SECONDS", "86400"))
    close_lock_ttl_seconds: int = int(os.getenv("CLOSE_LOCK_TTL_SECONDS", "600"))

    modal_app_name: str = os.getenv("MODAL_APP_NAME", "pulsefm-worker")
    modal_class_name: str = os.getenv("MODAL_CLASS_NAME", "MusicGenerator")
    modal_method_name: str = os.getenv("MODAL_METHOD_NAME", "generate")
    modal_function_name: str = os.getenv("MODAL_FUNCTION_NAME", "MusicGenerator.generate")


settings = Settings()
