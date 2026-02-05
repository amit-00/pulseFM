import os
from functools import lru_cache

import redis


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    url = os.getenv("REDIS_URL", "")
    if not url:
        raise ValueError("REDIS_URL is required")
    return redis.Redis.from_url(url, decode_responses=True)
