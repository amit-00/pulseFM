import json
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


def playback_current_key() -> str:
    return "pulsefm:playback:current"


def poll_tally_key(vote_id: str) -> str:
    return f"pulsefm:poll:{vote_id}:tally"


def poll_voted_key(vote_id: str) -> str:
    return f"pulsefm:poll:{vote_id}:voted"


async def set_playback_current_snapshot(client: redis.Redis, snapshot: dict, ttl_seconds: int) -> None:
    payload = json.dumps(snapshot, separators=(",", ":"))
    await client.set(playback_current_key(), payload, ex=max(1, int(ttl_seconds)))


async def get_playback_current_snapshot(client: redis.Redis) -> dict | None:
    raw = await client.get(playback_current_key())
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def set_playback_poll_status(
    client: redis.Redis,
    vote_id: str,
    status: str,
) -> None:
    snapshot = await get_playback_current_snapshot(client)
    if not snapshot:
        raise ValueError("playback current snapshot missing")

    poll = snapshot.get("poll")
    if not isinstance(poll, dict):
        raise ValueError("playback current snapshot missing poll")

    current_vote_id = poll.get("voteId")
    if current_vote_id != vote_id:
        raise ValueError("playback current snapshot voteId mismatch")

    poll["status"] = status
    snapshot["poll"] = poll

    ttl = await client.ttl(playback_current_key())  # type: ignore[misc]
    payload = json.dumps(snapshot, separators=(",", ":"))
    if ttl and int(ttl) > 0:
        await client.set(playback_current_key(), payload, ex=int(ttl))
    else:
        await client.set(playback_current_key(), payload)


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


POLL_OPEN_LUA = """
local playback_key = KEYS[1]
local tally_key = KEYS[2]
local voted_key = KEYS[3]

local playback_json = ARGV[1]
local playback_ttl = tonumber(ARGV[2])
local state_ttl = tonumber(ARGV[3])

redis.call("SET", playback_key, playback_json, "EX", playback_ttl)

redis.call("DEL", tally_key)
for i = 4, #ARGV, 2 do
  redis.call("HSET", tally_key, ARGV[i], ARGV[i + 1])
end
redis.call("EXPIRE", tally_key, state_ttl)

redis.call("DEL", voted_key)
redis.call("SADD", voted_key, "__init__")
redis.call("SREM", voted_key, "__init__")
redis.call("EXPIRE", voted_key, state_ttl)

return "ok"
"""


async def init_poll_open_atomic(
    client: redis.Redis,
    vote_id: str,
    playback_snapshot: dict,
    playback_ttl_seconds: int,
    state_ttl_seconds: int,
    options: list[str],
) -> None:
    tally_args: list[str] = []
    for option in options:
        tally_args.extend([option, "0"])
    playback_json = json.dumps(playback_snapshot, separators=(",", ":"))
    await client.eval(
        POLL_OPEN_LUA,
        3,
        playback_current_key(),
        poll_tally_key(vote_id),
        poll_voted_key(vote_id),
        playback_json,
        max(1, int(playback_ttl_seconds)),
        max(1, int(state_ttl_seconds)),
        *tally_args,
    )  # type: ignore[misc]


async def add_voted_session(client: redis.Redis, vote_id: str, session_id: str, ttl_seconds: int | None = None) -> bool:
    key = poll_voted_key(vote_id)
    added = (await client.sadd(key, session_id)) == 1  # type: ignore[misc]
    if ttl_seconds is not None:
        await client.expire(key, max(1, int(ttl_seconds)))
    return added


async def has_voted_session(client: redis.Redis, vote_id: str, session_id: str) -> bool:
    key = poll_voted_key(vote_id)
    return bool(await client.sismember(key, session_id))  # type: ignore[misc]


async def get_poll_tallies(client: redis.Redis, vote_id: str) -> dict[str, int]:
    raw = await client.hgetall(poll_tally_key(vote_id))  # type: ignore[misc]
    tallies: dict[str, int] = {}
    for option, value in raw.items():
        try:
            tallies[option] = int(value)
        except (TypeError, ValueError):
            tallies[option] = 0
    return tallies


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
