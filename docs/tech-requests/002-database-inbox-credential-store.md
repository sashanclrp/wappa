# Tech Request: Database-Backed Inbox Credential Store

**Priority:** High — blocks multi-inbox Symphonai deployments  
**Effort:** 1 focused session  
**Breaking:** No. Additive implementation behind existing interface.

---

## Why This Matters

Today, Wappa resolves inbox credentials from environment variables (`WP_PHONE_ID`, `WP_ACCESS_TOKEN`, `WP_BID`). This means:

1. **One inbox per deployment.** Every Wappa instance can only serve a single WhatsApp phone number. To add a second inbox, you deploy a second instance with different env vars.

2. **Credential rotation requires a restart.** When Meta rotates access tokens (which they do), you must redeploy to pick up new values. No hot-reload path.

3. **Symphonai can't manage inboxes dynamically.** The platform needs to onboard new WhatsApp numbers (Inboxes) at runtime — via admin UI, API, or automation. With env-var credentials, every inbox addition is an ops deployment.

4. **The contract already exists.** `IInboxCredentialStore` was introduced during the inbox_id refactor. `SettingsInboxCredentialStore` is the default. The only missing piece is a database-backed implementation that can resolve credentials for any registered inbox.

---

## What To Build

A `DatabaseInboxCredentialStore` that implements `IInboxCredentialStore` with:

1. **Redis cache layer** (hot path, ~1ms) — avoids DB queries on every webhook.
2. **Database fallback** — authoritative source for inbox registration and credentials.
3. **Registration via the host app** — Wappa provides the store; the host app writes inbox records.

### Interface (already exists)

```python
# wappa/domain/interfaces/inbox_credential_store.py

@dataclass(frozen=True)
class InboxCredentials:
    inbox_id: str
    access_token: str
    platform_account_id: str | None = None

class IInboxCredentialStore(ABC):
    async def get_credentials(self, inbox_id: str) -> InboxCredentials: ...
    async def validate_inbox(self, inbox_id: str) -> bool: ...
```

### New Implementation

```python
# wappa/domain/services/database_inbox_credential_store.py

class DatabaseInboxCredentialStore(IInboxCredentialStore):
    """
    Multi-inbox credential store with Redis cache + DB fallback.
    
    Lookup path:
      1. Redis hash: inbox:{inbox_id}:credentials → hit? return immediately
      2. Miss → query DB → populate Redis with TTL → return
      3. Not found → raise InboxNotFoundError
    """
    
    def __init__(self, db_session_factory, redis_manager, cache_ttl: int = 300): ...
    async def get_credentials(self, inbox_id: str) -> InboxCredentials: ...
    async def validate_inbox(self, inbox_id: str) -> bool: ...
    async def invalidate_cache(self, inbox_id: str) -> None: ...
```

### Redis Cache Key Design

```
inbox:{inbox_id}:credentials → Hash {
    "access_token": "EAAx...",
    "platform_account_id": "123456789",
    "platform": "whatsapp",
    "is_active": "true",
    "cached_at": "2026-05-16T12:00:00Z"
}
TTL: 300s (5 minutes)
```

### Database Schema (host-app owned)

Wappa does NOT own the database table — the host app does. Wappa provides the interface; the host writes to whichever storage it uses. However, the recommended schema for Symphonai:

```sql
CREATE TABLE wappa_inboxes (
    inbox_id        TEXT PRIMARY KEY,        -- phone_number_id for WhatsApp
    platform        TEXT NOT NULL DEFAULT 'whatsapp',
    access_token    TEXT NOT NULL,
    platform_account_id TEXT,                -- WABA ID for WhatsApp
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_wappa_inboxes_active ON wappa_inboxes (platform, is_active) WHERE is_active = TRUE;
```

### Wiring Into Wappa

The `IInboxCredentialStore` implementation is injected via the plugin system:

```python
app = (WappaBuilder()
    .with_whatsapp(...)
    .with_inbox_credential_store(DatabaseInboxCredentialStore(
        db_session_factory=get_session,
        redis_manager=redis_manager,
    ))
    .build())
```

Or for simple single-inbox deployments (unchanged):
```python
app = Wappa(whatsapp_token="...", whatsapp_phone_id="...", whatsapp_business_id="...")
# Automatically uses SettingsInboxCredentialStore — no change needed
```

### Where The Store Is Consumed (3 call sites)

1. **`MessengerFactory.create_messenger(inbox_id=)`** — resolves token to build WhatsApp client
2. **`whatsapp_dependencies.py` (API routes)** — resolves credentials for direct API message sending
3. **`WebhookController._create_request_handler()`** — validates inbox before processing webhook

All three currently instantiate `SettingsInboxCredentialStore()` inline. After this work, they receive the store from `app.state.inbox_credential_store` (set during plugin startup).

---

## What NOT To Build

- **No admin API for inbox CRUD.** That's Symphonai's responsibility. Wappa only reads.
- **No migration scripts.** The table is owned by the host app's migration system.
- **No token refresh logic.** Meta token rotation is an ops/automation concern. The store reads whatever the DB has.
- **No multi-platform credential dispatch.** Today this is WhatsApp-only. When Telegram lands, the store contract stays the same — the `inbox_id` just maps to a different platform identity.
- **No `SettingsInboxCredentialStore` deprecation.** It stays as the default for simple deployments.
- **No credential encryption at rest.** Out of scope — if the host needs encrypted token storage, it provides its own `IInboxCredentialStore` implementation.

---

## How To Execute

### Step 1: Inject the store via app state

Modify `WappaBuilder` and `Wappa` to accept an optional `IInboxCredentialStore`. Store it on `app.state.inbox_credential_store`. Default to `SettingsInboxCredentialStore()` when none is provided.

### Step 2: Update the 3 consumers to read from app state

Replace inline `SettingsInboxCredentialStore()` instantiation in:
- `wappa/domain/factories/messenger_factory.py`
- `wappa/api/dependencies/whatsapp_dependencies.py`
- `wappa/api/controllers/webhook_controller.py`

Instead, pull `request.app.state.inbox_credential_store` (or pass it via constructor for `MessengerFactory`).

### Step 3: Implement `DatabaseInboxCredentialStore`

New file: `wappa/domain/services/database_inbox_credential_store.py`

Logic:
```
get_credentials(inbox_id):
    # 1. Check Redis
    cached = await redis.hgetall(f"inbox:{inbox_id}:credentials")
    if cached and cached["is_active"] == "true":
        return InboxCredentials(...)
    
    # 2. Query DB
    async with db() as session:
        row = await session.execute(
            select(WappaInbox).where(
                WappaInbox.inbox_id == inbox_id,
                WappaInbox.is_active == True
            )
        )
        inbox = row.scalar_one_or_none()
    
    if not inbox:
        raise InboxNotFoundError(inbox_id)
    
    # 3. Populate Redis cache
    await redis.hset(f"inbox:{inbox_id}:credentials", mapping={...})
    await redis.expire(f"inbox:{inbox_id}:credentials", self.cache_ttl)
    
    return InboxCredentials(
        inbox_id=inbox.inbox_id,
        access_token=inbox.access_token,
        platform_account_id=inbox.platform_account_id,
    )

validate_inbox(inbox_id):
    try:
        await self.get_credentials(inbox_id)
        return True
    except InboxNotFoundError:
        return False

invalidate_cache(inbox_id):
    await redis.delete(f"inbox:{inbox_id}:credentials")
```

### Step 4: Add `invalidate_cache` to the interface

Extend `IInboxCredentialStore` with an optional `invalidate_cache(inbox_id)` method (default no-op in the base). This allows the host app to bust the cache when it updates credentials.

### Step 5: Add `WappaBuilder.with_inbox_credential_store()` method

```python
def with_inbox_credential_store(self, store: IInboxCredentialStore) -> Self:
    self._inbox_credential_store = store
    return self
```

### Step 6: Tests

- Test `DatabaseInboxCredentialStore` with mocked Redis + DB
- Test cache hit path (no DB call)
- Test cache miss path (DB query + cache write)
- Test `InboxNotFoundError` when inbox doesn't exist
- Test `invalidate_cache` busts the Redis key
- Test that `SettingsInboxCredentialStore` still works as default (regression)

---

## Acceptance Criteria

- [ ] `WappaBuilder.with_inbox_credential_store(store)` wires a custom store
- [ ] Default behavior (no custom store) uses `SettingsInboxCredentialStore` unchanged
- [ ] `DatabaseInboxCredentialStore` resolves from Redis cache on hot path
- [ ] Cache miss falls through to DB, populates cache, returns credentials
- [ ] Unknown `inbox_id` raises `InboxNotFoundError`
- [ ] `invalidate_cache(inbox_id)` removes the Redis key
- [ ] `MessengerFactory`, `whatsapp_dependencies`, and `WebhookController` use the injected store from app state
- [ ] No inline `SettingsInboxCredentialStore()` instantiation remains in consumers
- [ ] All existing tests pass
- [ ] New tests cover hit/miss/not-found/invalidation paths

---

## Performance Expectations

| Path | Latency | DB Calls |
|------|---------|----------|
| Redis cache hit | ~1ms | 0 |
| Redis miss + DB hit | ~5-15ms | 1 |
| Subsequent requests (same inbox) | ~1ms | 0 (cached for 5min) |
| Unknown inbox | ~5-15ms | 1 (then cached as "not found"? TBD) |

At 100 messages/sec to a single inbox, only 1 DB call every 5 minutes. The Redis layer absorbs all webhook traffic.

---

## Resolved Decisions

1. **Should "inbox not found" be cached?** If yes, a non-existent inbox won't hit DB repeatedly. If no, a newly registered inbox becomes available immediately. 
   - **Decision:** Don't cache negatives. The cost of a DB miss is low, and this avoids stale "not found" when onboarding new inboxes.

2. **Should the store model be a Wappa-owned SQLModel class, or just a raw query?**
   - **Decision:** Provide an optional `WappaInbox` SQLModel class that host apps can import or ignore. The database-backed store still accepts a `db_session_factory` and reads the host-owned `wappa_inboxes` table directly.

3. **Should `invalidate_cache` be in the interface or a separate concern?**
   - **Decision:** Add it to the interface with a default no-op. `SettingsInboxCredentialStore.invalidate_cache()` does nothing. `DatabaseInboxCredentialStore.invalidate_cache()` deletes the Redis key. Host apps call it when they update credentials.
