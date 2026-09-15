from redis.asyncio import Redis, from_url

from app.core.config import settings


def make_redis() -> Redis:
    return from_url(settings.redis_url, decode_responses=True)
