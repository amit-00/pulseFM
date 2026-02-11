import os
from functools import lru_cache

import redis


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    host = os.getenv("REDIS_HOST", "")
    port = int(os.getenv("REDIS_PORT", "6379"))
    if not host:
        raise ValueError("REDIS_HOST is required")
    return redis.Redis(host=host, port=port, decode_responses=True)


def current_poll_key() -> str:
    return "pulsefm:poll:current"


def poll_state_key(vote_id: str) -> str:
    return f"pulsefm:poll:{vote_id}:state"


def set_current_poll(client: redis.Redis, vote_id: str, ttl_seconds: int = 1) -> None:
    client.set(current_poll_key(), vote_id, ex=int(ttl_seconds))


def set_poll_state(
    client: redis.Redis,
    vote_id: str,
    status: str,
    opens_at_ms: int,
    closes_at_ms: int,
    ttl_seconds: int,
) -> None:
    key = poll_state_key(vote_id)
    pipeline = client.pipeline()
    pipeline.hset(key, mapping={
        "status": status,
        "opensAt": opens_at_ms,
        "closesAt": closes_at_ms,
    })
    pipeline.expire(key, max(1, int(ttl_seconds)))
    pipeline.execute()


def close_poll_state(client: redis.Redis, vote_id: str) -> None:
    client.hset(poll_state_key(vote_id), "status", "closed")
