import fakeredis.aioredis

from app.security import ratelimit


async def test_bucket_allows_up_to_capacity_then_denies() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    eng = "eng-1"
    # rate=5, capacity=5, temps figé -> 5 passent, la 6e est refusée
    for _ in range(5):
        assert await ratelimit.allow(redis, eng, rate=5, capacity=5, now=1000.0) is True
    assert await ratelimit.allow(redis, eng, rate=5, capacity=5, now=1000.0) is False
    await redis.aclose()


async def test_bucket_refills_over_time() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    eng = "eng-2"
    for _ in range(5):
        await ratelimit.allow(redis, eng, rate=5, capacity=5, now=2000.0)
    # vidé à t=2000 ; 1 seconde plus tard -> +5 jetons -> repasse
    assert await ratelimit.allow(redis, eng, rate=5, capacity=5, now=2001.0) is True
    await redis.aclose()


async def test_buckets_are_isolated_per_engagement() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    for _ in range(3):
        await ratelimit.allow(redis, "A", rate=3, capacity=3, now=10.0)
    assert await ratelimit.allow(redis, "A", rate=3, capacity=3, now=10.0) is False
    # un autre engagement a son propre seau
    assert await ratelimit.allow(redis, "B", rate=3, capacity=3, now=10.0) is True
    await redis.aclose()
