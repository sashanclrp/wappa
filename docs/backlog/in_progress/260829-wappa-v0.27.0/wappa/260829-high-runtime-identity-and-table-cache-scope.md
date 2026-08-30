---
version: 1.0.0
last_reviewed: 2026-08-30
status: done
author: sasha
urgency: high
owner: Wappa domain and persistence
blocked_by: none
decided_by: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
---

# Runtime identity and Table Cache scope

## Context

The first payload-routing slice passes raw WhatsApp `phone_number_id` values as
`inbox_id`. That works while WhatsApp is the only Platform. It stops being safe
when another Platform has the same native identifier.

The existing Table Cache API also names its namespace argument `inbox_id`, even
though Host Applications already use table-shaped caches for application and
Owner data. The implementation can store those values today, but the language
says every table belongs to an Inbox. That is false.

This PRD establishes qualified Platform identity and makes Table Cache the only
cache family that accepts a general context identifier.

## Code reality

Already present:

- `PlatformType` exists.
- WhatsApp Universal Models carry an Inbox ID derived from Meta's
  `phone_number_id`.
- `ICacheFactory` and cache key builders accept explicit Inbox values.
- Existing WhatsApp cache keys use the raw phone number ID. The first routing
  slice did not change those bytes.
- Root and persistence context docs contain early versions of System, Owner,
  and Inbox scope language.

Still missing or inconsistent:

- There is no `InboxRef` or `PlatformAccountRef` value object.
- Several public and internal contracts compare raw Inbox IDs across the whole
  application.
- Platform Account lookup accepts a bare string.
- Table Cache constructors and interfaces still call their namespace
  `inbox_id`.
- The repository instructions historically used Provider while the settled
  Wappa term is Platform. Documentation edits have started, but code and docs
  need a full audit.

## Scope

- Add immutable, validated `InboxRef` and `PlatformAccountRef` domain values.
- Use qualified identity wherever Wappa persists, caches, routes, or compares
  values across Platforms.
- Keep the WhatsApp mapping explicit at the WhatsApp adapter boundary.
- Reserve `SYSTEM_SCOPE = "__system__"` in Wappa persistence.
- Rename only the Table Cache namespace parameter from `inbox_id` to
  `context_id`.
- Supply a Wappa system-table builder that constructs `ITableCache` with the
  reserved System Scope.
- Preserve current Table Cache key values for positional and migrated keyword
  callers.
- Add conformance tests for memory, JSON, and Redis Table Cache adapters.

## Out of scope

- Adding Owner as a Wappa concept.
- Renaming `inbox_id` in User Cache, Expiry Cache, State Handler, PubSub, SSE,
  Cache Factory, or other conversational cache contracts.
- Creating `ITableGlobalCache`, `IInboxDirectoryTable`, or a new Redis pool.
- Changing the WhatsApp native Inbox ID away from Meta's `phone_number_id`.
- Defining identities for future Platform adapters beyond the qualified value
  objects.

## Domain model

```python
class InboxRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: PlatformType
    inbox_id: str


class PlatformAccountRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: PlatformType
    platform_account_id: str
```

Validation must reject blank values and values that cannot be encoded safely in
the existing cache key scheme. The values expose one Wappa-owned deterministic
cache namespace representation. Callers must not rebuild it with ad hoc string
concatenation.

For WhatsApp:

```text
InboxRef.platform                 = whatsapp
InboxRef.inbox_id                 = Meta phone_number_id
PlatformAccountRef.platform       = whatsapp
PlatformAccountRef.account_id     = Meta WABA ID
```

The actual field remains `platform_account_id`; the abbreviated line above only
describes the mapping.

## Cache namespace policy

Table Cache accepts three meanings for `context_id`:

| Scope | `context_id` value | Owner of the meaning |
| --- | --- | --- |
| System | exact constant `"__system__"` | Wappa |
| Host-defined business scope | a Host identifier such as Symphonai Owner ID | Host Application |
| Inbox | the Wappa-encoded Inbox namespace | Wappa and Platform adapter |

These scopes are independent. They do not form a parent-child tree and Wappa
does not infer one scope from another.

Only Table Cache gets this general namespace. Table Cache stores typed hash-map
records and supports Host DB-to-cache flows. Conversational cache families
still require an Inbox because their data has no valid System or Owner meaning.

## Compatibility contract

Changing this:

```python
RedisTableCache(inbox_id="123", ...)
```

to this:

```python
RedisTableCache(context_id="123", ...)
```

is a naming migration. It must not change the constructed Redis key.

Positional calls keep working. Calls that name `inbox_id=` fail at construction
until the Host changes the keyword to `context_id=`. Do not add a long-lived
alias that preserves two public terms for one argument. The migration guide and
Symphonai PRD must include a repository-wide keyword audit.

Existing WhatsApp Inbox cache keys must remain byte-identical in v0.27 where
the namespace is already a raw phone number ID. New cross-Platform tables use
the Wappa-owned qualified encoding. Tests must pin both cases so a later cleanup
cannot silently orphan deployed Redis data.

## Proposed module ownership

```text
wappa/domain/inbox/
  identity.py              InboxRef and PlatformAccountRef

wappa/persistence/
  scope.py                 SYSTEM_SCOPE and namespace rules
  ...                      existing ITableCache and adapters
```

The system-table builder belongs beside Table Cache construction. It reuses the
configured persistence backend and pool; it does not know about Inbox Directory
records.

## Implementation notes

- Make both reference models hashable or provide stable tuple semantics so the
  runtime can deduplicate and sort fan-out candidates.
- Define ordering explicitly. Sorting must include Platform before native ID.
- Keep serialization versioned enough that a future delimiter change can be
  migrated without guessing.
- Reject `"__system__"` as a Platform-native Inbox ID only if the qualified
  encoding could collide. Prefer an encoding that makes the scopes distinct by
  construction.
- Audit `inbox_id=` keyword calls only for Table Cache classes. A global search
  and replace would corrupt other cache contracts.
- Ensure Table Cache adapter protocols, factories, in-memory fixtures, JSON
  persistence, Redis implementations, and generated examples agree on the new
  parameter name.

## Verification

Tests must prove:

- Two Platforms may use the same raw `inbox_id` without identity or key
  collision.
- Two Platforms may use the same raw `platform_account_id` without reverse
  index collision.
- `InboxRef` and `PlatformAccountRef` reject invalid values and serialize
  deterministically.
- The system-table builder always uses the exact `SYSTEM_SCOPE` constant.
- A Host-defined Owner context can use Table Cache without Wappa learning Owner
  semantics.
- Existing positional Table Cache construction creates the same key as before.
- Migrating `inbox_id="123"` to `context_id="123"` changes no stored key.
- A stale `inbox_id=` keyword raises a direct constructor/type error with no
  hidden fallback.
- User, expiry, state, SSE, and other Inbox caches still require Inbox identity.
- Memory, JSON, and Redis Table Cache adapters pass the same contract suite.

Run:

```bash
uv run ruff check .
uv run mypy wappa
uv run pytest -q
git diff --check
```

## Documentation obligations

- Root `CONTEXT.md`: Inbox Reference, Platform Account Reference, Platform, and
  qualified uniqueness.
- Persistence `CONTEXT.md`: Table Cache Context, System Scope, Host-defined
  business scope, and Inbox scope.
- Root and persistence `ARCHITECTURE.md`: identity ownership and dependency
  direction.
- `docs/public-contract.md`: value models, Table Cache rename, compatibility,
  and System Scope reservation.
- Migration guide and CLI examples: keyword replacement without Redis migration.
- `AGENTS.md`: Platform language and qualified identity rules.

## Open questions

None. The grilling session settled identity uniqueness, cache scope, naming,
and compatibility behavior.

## Exit criteria

- Both value objects exist in the domain layer and all cross-Platform routing,
  directory, and reverse-index code uses them.
- `ITableCache` and every implementation use `context_id` for construction.
- Wappa exposes the reserved System Scope and a ready-to-use system-table
  builder through the supported public imports.
- No new Redis abstraction was added for application-scoped tables.
- Existing WhatsApp keys remain readable and writable without a data migration.
- Non-Table Cache contracts still use Inbox terminology.
- Contract tests pass on every supported persistence backend.
- The listed DDD and public-contract documents match the implementation.
