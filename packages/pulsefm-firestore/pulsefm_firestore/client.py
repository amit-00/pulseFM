from functools import lru_cache

from google.cloud.firestore import AsyncClient


@lru_cache(maxsize=1)
def get_firestore_client() -> AsyncClient:
    return AsyncClient()
