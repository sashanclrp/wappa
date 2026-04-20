from collections.abc import Callable

from ..domain.interfaces.cache_factory import ICacheFactory


def _load_redis_factory() -> type[ICacheFactory]:
    from .redis.redis_cache_factory import RedisCacheFactory

    return RedisCacheFactory


def _load_json_factory() -> type[ICacheFactory]:
    from .json.json_cache_factory import JSONCacheFactory

    return JSONCacheFactory


def _load_memory_factory() -> type[ICacheFactory]:
    from .memory.memory_cache_factory import MemoryCacheFactory

    return MemoryCacheFactory


_FACTORY_LOADERS: dict[str, tuple[Callable[[], type[ICacheFactory]], str]] = {
    "redis": (_load_redis_factory, "Redis"),
    "json": (_load_json_factory, "JSON"),
    "memory": (_load_memory_factory, "Memory"),
}


def create_cache_factory(cache_type: str) -> type[ICacheFactory]:
    normalized = cache_type.strip().lower()
    loader_info = _FACTORY_LOADERS.get(normalized)
    if loader_info is None:
        raise ValueError(
            f"Unsupported cache_type: {cache_type}. "
            f"Supported types: 'redis', 'json', 'memory'"
        )

    loader, backend_label = loader_info
    try:
        return loader()
    except ImportError as e:
        raise ImportError(
            f"{backend_label} dependencies not available for "
            f"cache_type='{normalized}': {e}"
        ) from e


def get_cache_factory(
    cache_type: str, *, validate_redis_url: bool = True
) -> type[ICacheFactory]:
    normalized = cache_type.strip().lower()

    if normalized == "redis" and validate_redis_url:
        from ..core.config.settings import settings

        if not settings.has_redis:
            raise ValueError(
                "Redis URL not configured. Set REDIS_URL environment variable "
                "or use a different cache_type"
            )

    return create_cache_factory(normalized)
