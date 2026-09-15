"""Rate limiter par engagement — token bucket atomique dans Redis (§12.3).

Chaque engagement a son seau : il se remplit à `rate` jetons/seconde jusqu'à
`capacity`. Une requête consomme un jeton ; s'il n'y en a pas, elle est refusée.
Le calcul est fait côté Redis (script Lua) pour être atomique malgré la
concurrence des workers.
"""

from __future__ import annotations

import time

from redis.asyncio import Redis

# refill + consommation atomiques
_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
local delta = now - ts
if delta < 0 then delta = 0 end
tokens = math.min(capacity, tokens + delta * rate)
local allowed = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 3600)
return allowed
"""


def bucket_key(engagement_id: str) -> str:
    return f"ratelimit:{engagement_id}"


async def allow(
    redis: Redis,
    engagement_id: str,
    *,
    rate: float,
    capacity: float | None = None,
    requested: int = 1,
    now: float | None = None,
) -> bool:
    """True si la requête passe (jeton consommé), False si le seau est vide."""
    if capacity is None:
        capacity = max(rate, 1.0)
    script = redis.register_script(_LUA)
    result = await script(
        keys=[bucket_key(engagement_id)],
        args=[rate, capacity, now if now is not None else time.time(), requested],
    )
    return bool(int(result))
