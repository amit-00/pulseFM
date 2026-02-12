import os
from functools import lru_cache

import redis.asyncio as redis


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


def poll_tally_key(vote_id: str) -> str:
    return f"pulsefm:poll:{vote_id}:tally"


def poll_voted_key(vote_id: str) -> str:
    return f"pulsefm:poll:{vote_id}:voted"


async def set_current_poll(client: redis.Redis, vote_id: str, ttl_seconds: int = 1) -> None:
    await client.set(current_poll_key(), vote_id, ex=int(ttl_seconds))


async def set_poll_state(
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
    await pipeline.execute()


async def init_poll_tally(client: redis.Redis, vote_id: str, options: list[str], ttl_seconds: int) -> None:
    key = poll_tally_key(vote_id)
    mapping = {option: 0 for option in options}
    pipeline = client.pipeline()
    pipeline.hset(key, mapping=mapping)
    pipeline.expire(key, max(1, int(ttl_seconds)))
    await pipeline.execute()


async def init_poll_voted_set(client: redis.Redis, vote_id: str, ttl_seconds: int) -> None:
    key = poll_voted_key(vote_id)
    pipeline = client.pipeline()
    pipeline.sadd(key, "__init__")
    pipeline.srem(key, "__init__")
    pipeline.expire(key, max(1, int(ttl_seconds)))
    await pipeline.execute()


async def add_voted_session(client: redis.Redis, vote_id: str, session_id: str, ttl_seconds: int | None = None) -> bool:
    key = poll_voted_key(vote_id)
    added = (await client.sadd(key, session_id)) == 1  # type: ignore[misc]
    if ttl_seconds is not None:
        await client.expire(key, max(1, int(ttl_seconds)))
    return added


VOTE_LUA = """
local voted_key = KEYS[1]
local tally_key = KEYS[2]
local session_id = ARGV[1]
local option = ARGV[2]

local added = redis.call("SADD", voted_key, session_id)
if added == 1 then
  redis.call("HINCRBY", tally_key, option, 1)
  return 1
end
return 0
"""


async def record_vote_atomic(client: redis.Redis, vote_id: str, session_id: str, option: str) -> bool:
    voted_key = poll_voted_key(vote_id)
    tally_key = poll_tally_key(vote_id)
    result = await client.eval(VOTE_LUA, 2, voted_key, tally_key, session_id, option)  # type: ignore[misc]
    return int(result) == 1


async def close_poll_state(client: redis.Redis, vote_id: str) -> None:
    await client.hset(poll_state_key(vote_id), "status", "closed")  # type: ignore[misc]
