from arq.connections import ArqRedis

from app.core.config import settings


def make_arq_pool() -> ArqRedis:
    """Construit le pool arq sans se connecter (paresseux, comme `make_redis`).

    Ne pas utiliser `arq.create_pool` ici : il ping Redis immédiatement et lève
    si Redis n'est pas encore joignable, ce qui casserait le lifespan de la
    gateway (voir `/health/ready`, censé dégrader proprement).
    """
    return ArqRedis.from_url(settings.redis_url)  # type: ignore[no-any-return]
