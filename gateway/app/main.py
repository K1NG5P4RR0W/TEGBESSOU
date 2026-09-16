"""TEGBESSOU API Gateway — B0.3 (auth + RBAC).

/health       : liveness.
/health/ready : readiness (PostgreSQL + Redis).
/auth/*, /users : authentification et gestion des comptes.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.engagements import router as engagements_router
from app.api.users import router as users_router
from app.core.db import make_engine, make_sessionmaker
from app.core.redis_client import make_redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = make_engine()
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.redis = make_redis()
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await engine.dispose()


app = FastAPI(title="TEGBESSOU API Gateway", version="0.3.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(engagements_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}


@app.get("/health/ready")
async def ready(response: Response) -> dict[str, Any]:
    db_ok = False
    redis_ok = False
    try:
        async with app.state.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    try:
        redis_ok = bool(await app.state.redis.ping())
    except Exception:
        redis_ok = False
    is_ready = db_ok and redis_ok
    if not is_ready:
        response.status_code = 503
    return {"status": "ready" if is_ready else "not_ready", "db": db_ok, "redis": redis_ok}
