"""Compatibility import path for a common repositories misspelling."""

from pulsefm_shared.repositories import (
    DatabaseProtocol,
    QueryProtocol,
    SongRecord,
    SongRepository,
)

__all__ = ["DatabaseProtocol", "QueryProtocol", "SongRecord", "SongRepository"]
