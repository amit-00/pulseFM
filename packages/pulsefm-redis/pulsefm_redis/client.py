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


FIXED_WINDOW_LUA = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local current = redis.call("INCR", key)
if current == 1 then
  redis.call("EXPIRE", key, window)
end
return current
"""


async def fixed_window_allow(client: redis.Redis, key: str, limit: int, window_seconds: int) -> bool:
    current = await client.eval(FIXED_WINDOW_LUA, 1, key, window_seconds)  # type: ignore[misc]
    return int(current) <= limit


TOKEN_BUCKET_LUA = """
local bucket_key = KEYS[1]
local rps_key = KEYS[2]
local capacity = tonumber(ARGV[1])
local refill_per_ms = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local tokens_requested = tonumber(ARGV[4])
local rps_limit = tonumber(ARGV[5])

local tokens = tonumber(redis.call("HGET", bucket_key, "tokens"))
local last = tonumber(redis.call("HGET", bucket_key, "ts"))
if not tokens then tokens = capacity end
if not last then last = now_ms end

local delta = now_ms - last
if delta < 0 then delta = 0 end
tokens = math.min(capacity, tokens + (delta * refill_per_ms))

local rps = redis.call("INCR", rps_key)
if rps == 1 then
  redis.call("PEXPIRE", rps_key, 1000)
end
if rps > rps_limit then
  redis.call("HSET", bucket_key, "tokens", tokens, "ts", now_ms)
  return -1
end

if tokens < tokens_requested then
  redis.call("HSET", bucket_key, "tokens", tokens, "ts", now_ms)
  return 0
end

tokens = tokens - tokens_requested
redis.call("HSET", bucket_key, "tokens", tokens, "ts", now_ms)
return 1
"""


async def token_bucket_allow(
    client: redis.Redis,
    bucket_key: str,
    rps_key: str,
    capacity: int,
    refill_per_ms: float,
    tokens: int,
    rps_limit: int,
) -> bool:
    now_ms = int((await client.time())[0] * 1000)  # type: ignore[misc]
    result = await client.eval(
        TOKEN_BUCKET_LUA,
        2,
        bucket_key,
        rps_key,
        capacity,
        refill_per_ms,
        now_ms,
        tokens,
        rps_limit,
    )  # type: ignore[misc]
    return int(result) == 1
