# RateLimitPlugin

`RateLimitPlugin` registers local, per-process route-level rate limit profiles.
It does not install global middleware; routes opt in explicitly with
`Depends(rate_limit("profile"))`.

```python
from fastapi import Depends
from wappa.core.plugins import RateLimitPlugin, RateLimitProfile, rate_limit

plugin = RateLimitPlugin(
    [
        RateLimitProfile(
            name="webhook",
            limit=60,
            window_seconds=60,
            key_by="inbox_id_and_client_ip",
        )
    ]
)

@router.post(
    "/webhooks/{inbox_id}",
    dependencies=[Depends(rate_limit("webhook"))],
)
async def webhook(inbox_id: str):
    ...
```

## Public API

| Surface | Purpose |
|---|---|
| `RateLimitProfile(name, limit, window_seconds, key_by="client_ip")` | Named fixed-window policy. |
| `RateLimitPlugin(profiles=[...])` | Stores a local limiter on `app.state.wappa_rate_limiter` during startup. |
| `rate_limit(profile_name)` | FastAPI dependency factory for route-level opt-in. |

Supported key modes:

- `client_ip`
- `inbox_id`
- `inbox_id_and_client_ip`

When a request exceeds the profile limit, Wappa raises HTTP 429 and includes a
`Retry-After` header. Unknown profiles and missing plugin state are
configuration errors; Wappa does not fail open.

This plugin is intentionally local. Redis-backed, distributed, or global quota
limiting is not part of the current contract.
