# Isolation tests

```python
import asyncio
from wappa.domain.inbox import InboxRef
from wappa.persistence.cache_factory import create_cache_factory
from wappa.schemas.core.types import PlatformType

WA = InboxRef.whatsapp("1022535354280031")
IG_A = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17840001")
IG_B = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17840002")

async def test_same_native_id_never_shares_state():
    factories = [create_cache_factory("memory")(inbox_id=ref.cache_namespace, user_id="12345")
                 for ref in (WA, IG_A, IG_B)]
    caches = [f.create_state_cache() for f in factories]
    await asyncio.gather(*(c.upsert("flow", {"owner": i}, ttl=60) for i, c in enumerate(caches)))
    assert [(await c.get("flow"))["owner"] for c in caches] == [0, 1, 2]

async def test_miss_is_none_and_delete_clears():
    cache = create_cache_factory("memory")(inbox_id=IG_A.cache_namespace, user_id="u").create_state_cache()
    assert await cache.get("missing") is None
    await cache.upsert("flow", {"step": "name"}, ttl=60)
    await cache.delete("flow")
    assert await cache.get("flow") is None
```

For Redis, run the same tests against a disposable Redis with `create_cache_factory("redis")` after Wappa's Redis plugin has started. Never point tests at production Redis.
