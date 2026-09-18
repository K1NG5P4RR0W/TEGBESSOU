from redis.asyncio import Redis, from_url

from app.core.config import settings


def make_redis() -> Redis:
    # redis.asyncio.from_url n'a pas d'annotations dans la version <6 imposée
    # par arq (E1) — voir gateway/pyproject.toml.
    return from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-any-return,no-untyped-call]
