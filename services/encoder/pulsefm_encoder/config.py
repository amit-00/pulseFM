import os
from dataclasses import dataclass


def _normalize_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    return prefix if prefix.endswith("/") else f"{prefix}/"


_raw_bucket = os.getenv("RAW_BUCKET", "pulsefm-generated-songs")


@dataclass(frozen=True)
class Settings:
    raw_bucket: str = _raw_bucket
    raw_prefix: str = _normalize_prefix(os.getenv("RAW_PREFIX", "raw/"))
    encoded_bucket: str = os.getenv("ENCODED_BUCKET", _raw_bucket)
    encoded_prefix: str = _normalize_prefix(os.getenv("ENCODED_PREFIX", "encoded/"))
    encoded_cache_control: str = os.getenv("ENCODED_CACHE_CONTROL", "public,max-age=300,s-maxage=3600")
    songs_collection: str = os.getenv("SONGS_COLLECTION", "songs")


settings = Settings()
