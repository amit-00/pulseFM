"""Persistence adapters shared by PulseFM Python apps."""

from pulsefm_shared.repositories.song_repository import (
    DatabaseProtocol,
    QueryProtocol,
    SongRecord,
    SongRepository,
)

__all__ = ["DatabaseProtocol", "QueryProtocol", "SongRecord", "SongRepository"]