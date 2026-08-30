# ADR-0011: Wappa-owned encrypted Inbox Directory under the System Scope

## Status

Accepted (2026-08-30). Decided in `docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md`, sections 1 through 4.

## Context

Explicit multi-Inbox routing cannot query the Host database on every webhook, send, media lookup, or HTTP request, and it cannot let each Host invent its own Redis row, reverse index, validation rules, and token-rotation behaviour. The first v0.27 candidate exposed an open-ended `IInboxCredentialStore`, a `DatabaseInboxCredentialStore` that prescribed a `wappa_inboxes` SQL table, plaintext tokens in Redis hashes, an unqualified WABA lookup, and cache invalidation by convention. Each of those is expensive to unwind once a Host has deployed against it.

## Decision

`InboxRoutingMode` selects exactly one credential authority per process — `legacy` (the `WP_*` bundle) or `explicit` (the Inbox Directory). The two are mutually exclusive; Wappa never falls back from one to the other, and no `auto` mode exists.

1. **Wappa owns the directory.** `InboxDirectoryTable` (persistence) and `InboxDirectory` (domain service) are concrete Wappa modules. Hosts cannot replace the model, cache shape, TTL rules, indexes, or mutation behaviour.
2. **Hosts own their durable schema** and adapt it through one read-only port, `IInboxDirectorySource`, with `get_inbox(inbox_ref)` and `list_inboxes_for_platform_account(account_ref)`. Wappa never prescribes SQL. The internal `IInboxCredentialResolver` read port is not a Host extension point; Wappa installs both production implementations (legacy settings adapter, Inbox Directory).
3. **The directory reuses `ITableCache`** under the reserved System Scope `SYSTEM_SCOPE = "__system__"`. No `ITableGlobalCache`, no directory-specific Redis adapter, no raw Redis Set. Redis is the production backend; memory and JSON pass the same conformance suite. Only Table Cache accepts a general `context_id`.
4. **Freshness:** active primary rows and active Platform Account indexes have a 60-minute sliding TTL renewed on every validated hit. Inactive, absent, and empty-account rows have a fixed 60-minute TTL that reads never renew. The Host database stays durable authority; a miss makes one source call. Source or cache failures never become negative records.
5. **Only Wappa mutates the directory.** Hosts commit their durable state and then call the source-driven, idempotent `refresh_inbox(inbox_ref)` (or `deactivate_inbox`). Wappa writes the primary row before derived indexes, repairs partial work on retry, and evicts cached Messengers. There is no `upsert_inbox(record)` and no normal hard-delete command.
6. **Version rules:** `credential_version` is a positive integer monotonic across the whole lifetime of one `InboxRef`, including deactivation and recreation. Higher wins; lower is stale; equal is accepted only for an identical canonical record. `updated_at` is operational evidence, never ordering.
7. **Encrypted canonical records.** Wappa encrypts every credential with `SYSTEM_TOKEN_ENC_KEY` (Fernet) into a context-bound `EncryptedSecretEnvelope` that binds format version, Platform, `inbox_id`, and the credential field name. Hosts persist the envelope and never decrypt it. Reads accept `SYSTEM_TOKEN_ENC_PREVIOUS_KEYS` (MultiFernet semantics), rewrite cache rows under the active key, and `rotate_encrypted_record` re-encrypts durable rows without exposing plaintext. Tokens are never hashed: Meta needs the exact bearer value.
8. **The reverse index is a projection, not authority.** Every listed member is checked against its primary record (active, same `InboxRef`, same `PlatformAccountRef`). A stale member triggers one synchronous source reload and repair; repair failure is `503`, never a dispatched subset. A confirmed empty account is a fixed-TTL empty index answered with `400`.

## Consequences

- Hosts write no cache rows and no cipher; their integration surface is one source adapter plus `InboxCredentialService.create_active_record` / `rotate_active_record` before persistence and `refresh_inbox` after commit.
- Several Inbox records may carry the same physical Meta token; each carries its own envelope, so copying ciphertext between rows fails integrity.
- A directory outage is `InboxDirectoryUnavailableError` (503), a confirmed unknown or inactive Inbox is `InboxNotFoundError`, a wrong-account relation is `InboxMembershipError`, and an unusable envelope is `InboxCredentialIntegrityError`. Nothing collapses to "unknown Inbox".
- The 60-minute sliding TTL means a deactivated Inbox stays usable only until the Host calls `deactivate_inbox`; TTL is never the revocation mechanism.
- The JSON backend keeps one file-level expiry per scope, so sliding and fixed TTLs cannot differ there; it remains a single-process development backend.
- Removing an old encryption key is safe only after durable re-encryption, the 60-minute maximum directory TTL, and the deployment overlap window have all passed. Losing every accepted key makes stored credentials unrecoverable.

## Alternatives considered

1. Keep `IInboxCredentialStore` open for Host implementations. Rejected: Hosts could change active-Inbox rules, fan-out, renewal, and error semantics behind the same method names.
2. Let Hosts write directory rows or pass canonical records to an `upsert`. Rejected: a Host could commit one value and push another into Redis, and Wappa could not guarantee validation, indexes, or ordering.
3. A directory-specific Redis adapter or Redis Set for the WABA index. Rejected: it would fork the persistence contract and make memory/JSON conformance impossible.
4. `SecretStr` alone or hashed tokens at rest. Rejected: `SecretStr` only masks representations, and a hash cannot be placed in a bearer header.
5. Redis as runtime authority with Hosts publishing records. Rejected in favour of read-through so the Host database remains the single durable authority.
