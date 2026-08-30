---
version: 1.0.0
last_reviewed: 2026-08-30
status: done
author: sasha
urgency: high
owner: Wappa domain, security, and persistence
blocked_by: runtime identity and Table Cache scope
decided_by: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
---

# Encrypted Inbox Directory

## Context

Explicit multi-Inbox routing cannot query the Host database on every webhook,
send, media lookup, or HTTP request. It also cannot let each Host invent its
own Redis row, reverse index, validation rules, and token-rotation behavior.

Wappa will ship one mandatory `InboxDirectoryTable`. A Host maps its own durable
schema to Wappa's canonical records through a read-only source. Wappa owns every
cache write and every secret operation.

## Code reality

The first implementation slice added a public `IInboxCredentialStore`, a
settings implementation, and a database implementation that prescribes a
`wappa_inboxes` SQL table. It caches credentials and can enumerate Inboxes by
WABA. It also added Messenger invalidation calls.

That design is replaced by this PRD:

- The Host must not define directory storage behavior.
- Wappa must not own or prescribe the Host's SQL schema.
- `SecretStr` alone does not encrypt Redis or database values.
- Cache invalidation by convention cannot guarantee immediate deactivation.
- A plain WABA string cannot safely index several Platforms.

## Scope

- Define Wappa-owned, Platform-discriminated credential records.
- Ship the WhatsApp active and inactive record variants for v0.27.
- Define the encrypted secret envelope and Fernet key policy.
- Expose Wappa commands for creation, rotation, refresh, and deactivation.
- Define the Host's read-only `IInboxDirectorySource` port.
- Implement the concrete `InboxDirectoryTable` on `ITableCache` under System
  Scope.
- Implement read-through lookup, sliding and fixed TTL behavior, version checks,
  negative records, and Messenger eviction.
- Keep the internal credential resolver as a dependency-inversion port and test
  seam.

## Out of scope

- Owning any Host database table or migration.
- Letting a Host substitute its own directory implementation or cache schema.
- Hashing access tokens.
- Designing Instagram, Telegram, iMessage, or other Platform credentials.
- Application-secret encryption for `META_APP_SECRET`.
- Full Host outbox infrastructure. Hosts may add one, but Wappa's commands must
  work without it.

## Public and internal contracts

### Canonical records

Use a status discriminator so an inactive row cannot accidentally carry usable
credential material.

```python
class EncryptedSecretEnvelope(BaseModel):
    format_version: Literal[1] = 1
    ciphertext: SecretStr


class WhatsAppActiveInboxCredentialRecord(BaseModel):
    schema_version: Literal[1] = 1
    platform: Literal[PlatformType.WHATSAPP]
    inbox_id: str
    platform_account_id: str
    status: Literal["active"]
    access_token: EncryptedSecretEnvelope
    credential_version: int
    updated_at: datetime


class WhatsAppInactiveInboxCredentialRecord(BaseModel):
    schema_version: Literal[1] = 1
    platform: Literal[PlatformType.WHATSAPP]
    inbox_id: str
    platform_account_id: str
    status: Literal["inactive"]
    credential_version: int
    updated_at: datetime
```

The implementation may factor shared fields into base models. The serialized
contract must keep the status and Platform discriminators visible. `updated_at`
must include a timezone. `credential_version` must be a positive, monotonic
integer across the full lifetime of one `InboxRef`, including deactivation and
later recreation.

The public union is Platform-discriminated:

```python
InboxCredentialRecord = Annotated[
    WhatsAppActiveInboxCredentialRecord
    | WhatsAppInactiveInboxCredentialRecord,
    Field(discriminator="platform"),
]
```

If Pydantic requires nested discrimination because status also varies, preserve
the same serialized shape and type safety. v0.27 ships only WhatsApp members.

The field name `access_token` states what the WhatsApp adapter needs. Keep the
legacy environment variable named `WP_ACCESS_TOKEN` for compatibility. Do not
rename it `META_ACCESS_TOKEN`; Meta token types, permissions, apps, and assigned
assets do not promise one universal credential for every Meta product.

### Host source

```python
class IInboxDirectorySource(Protocol):
    async def get_inbox(
        self,
        inbox_ref: InboxRef,
    ) -> InboxCredentialRecord | None: ...

    async def list_inboxes_for_platform_account(
        self,
        account_ref: PlatformAccountRef,
    ) -> tuple[InboxCredentialRecord, ...]: ...
```

The Host chooses its tables, column names, repositories, and business
transactions. The adapter returns Wappa's encrypted canonical records. It does
not return raw Redis data and never decrypts the token.

Directory cache misses, activation refreshes, rotations, deactivations, and
reconciliation use the Host's primary database path by default. A Host that
routes these reads to a replica accepts the stale-security risk itself.

### Internal resolver

`IInboxCredentialResolver` remains internal. It gives inbound, outbound, and
test code a small read contract without exposing the directory as a Host
extension point. Production construction always installs Wappa's resolver.

### Wappa-owned commands

Wappa must expose supported application services with behavior equivalent to:

```python
create_active_record(..., access_token: SecretStr) -> ActiveRecord
rotate_active_record(previous, ..., access_token: SecretStr) -> ActiveRecord
rotate_encrypted_record(record) -> InboxCredentialRecord
refresh_inbox(inbox_ref: InboxRef) -> InboxCredentialRecord
deactivate_inbox(inbox_ref: InboxRef) -> InactiveRecord
```

Hosts call Wappa before persisting an active or rotated credential. Wappa
validates the fields, encrypts the plaintext token, and returns the canonical
record. The Host stores that returned record. It must not recreate the envelope
or decrypt it.

After the Host transaction commits, it calls `refresh_inbox(inbox_ref)`. The
command reloads through the source, validates the record, updates the primary
directory row and account index, and evicts cached Messenger/client objects.

`deactivate_inbox` follows the same source-driven rule. The Host commits the
inactive durable state first, then asks Wappa to refresh. Wappa stores an
inactive negative record. There is no normal hard-delete command in v0.27.

## Encryption boundary

Explicit mode requires:

```text
SYSTEM_TOKEN_ENC_KEY=<active Fernet key>
SYSTEM_TOKEN_ENC_PREVIOUS_KEYS=<optional comma-separated older Fernet keys>
```

Wappa uses Fernet through its high-level API. New writes use the active key.
Reads try the active key first and then the ordered previous keys, following
MultiFernet semantics.

The encrypted plaintext must bind at least:

```text
format_version
platform
inbox_id
credential_field_name
plaintext credential
```

On decrypt, Wappa checks those bound values against the record being resolved.
Copying one Inbox's ciphertext into another record must fail with
`InboxCredentialIntegrityError`.

If a cache read succeeds with a previous key, Wappa rewrites the cached envelope
under the active key. Durable migration uses
`rotate_encrypted_record(record)`. That method returns a re-encrypted record and
never exposes plaintext to the Host.

The Host enumerates and persists its own durable rows. Remove an old key only
after:

- every durable record has been re-encrypted and committed;
- every deployment can read the active key;
- at least the 60-minute maximum directory TTL has passed since the last old
  cache write; and
- the deployment overlap window has ended.

Losing every accepted key makes the stored credentials unrecoverable. Startup
validation must report configuration errors without echoing key material.

Wappa guarantees redaction and prevents plaintext or ciphertext from appearing
in logs, events, health data, exceptions, and model representations. The Host
still owns Redis TLS, authentication, network access, persistence encryption,
backups, and secret distribution.

## Directory storage and freshness

`InboxDirectoryTable` uses the existing Table Cache backend with:

```text
context_id = "__system__"
```

Wappa owns table names, primary key encoding, record serialization, secondary
indexes, TTLs, and compare-and-set behavior. Hosts receive a ready-to-use
builder through Wappa's supported application construction.

Freshness rules:

| Record | TTL | Read behavior |
| --- | --- | --- |
| Active Inbox primary row | 60 minutes | renew on every successful hit |
| Active Platform Account index | 60 minutes | renew on every successful hit |
| Inactive Inbox row | fixed 60 minutes | do not renew |
| Confirmed absent Inbox row | fixed 60 minutes | do not renew |
| Confirmed empty account index | fixed 60 minutes | do not renew |

The Host database remains durable authority. A cache miss makes one source call,
validates the result, stores it, and returns it. Source or cache failures do not
become negative records.

## Version and mutation rules

- A higher `credential_version` wins.
- A lower version is rejected as stale.
- An equal version is accepted only when the canonical record is identical.
- An equal identical retry still repairs secondary indexes and evicts any stale
  Messenger/client cache.
- Write the primary row before derived indexes. A retry repairs partial work.
- Mutation commands are idempotent for the same canonical input.
- The source must never reuse a lower version after deactivation or recreation.
- `updated_at` provides operational evidence. It never decides ordering.

A Host may use an outbox or reconciler after its business transaction. That
worker calls the same Wappa refresh command; it does not write Redis rows.

## Proposed module ownership

```text
wappa/domain/inbox/
  credentials.py           canonical records and discriminated unions
  errors.py                typed directory and integrity failures
  ports.py                 source and internal resolver contracts
  services.py              read-through and mutation orchestration

wappa/core/security/
  credential_codec.py      Fernet encrypt, decrypt, and re-encrypt

wappa/persistence/
  inbox_directory.py       concrete ITableCache-backed directory
```

The persistence class cannot import Host repositories or WhatsApp HTTP clients.
The WhatsApp adapter receives decrypted credential capability from the internal
resolver; API routes never see the token.

## Failure behavior

- Confirmed absent or inactive Inbox: `InboxNotFoundError` at the domain seam.
- Redis or source unavailable: `InboxDirectoryUnavailableError`.
- Invalid envelope, wrong context binding, or no accepted key:
  `InboxCredentialIntegrityError`.
- Stale version or equal-version conflict: a typed mutation conflict. It must
  not silently overwrite the newer cache value.

HTTP mappings belong to the boundary PRD. Domain errors must not contain secret
values or full records.

## Verification

The contract suite must cover memory, JSON, and Redis Table Cache backends:

- Warm active reads do not call the source and renew the TTL.
- A cold known Inbox calls the source once and populates the primary row.
- Concurrent misses do not corrupt the record or account index.
- Inactive and absent rows stop repeated database reads but never renew.
- Cache or source outages raise an unavailable error and create no negative row.
- Higher, lower, equal-identical, and equal-conflicting versions follow the
  stated rules.
- Partial primary/index writes repair on retry.
- Deactivation removes active index membership, stores no token, and evicts the
  Messenger/client cache.
- Reactivation requires a higher lifetime version.
- Two Inboxes may contain the same physical access token without sharing
  identity or envelope context.
- Plaintext never appears in serialized records, logs, health data, event data,
  or exception messages.
- Ciphertext copied to another Inbox or field fails integrity validation.
- Active-key and previous-key reads work; old-key cache reads rewrite under the
  active key.
- Durable re-encryption returns a new envelope without exposing plaintext.
- Explicit-mode startup rejects a missing or malformed encryption key.

## Documentation obligations

- Add Inbox Directory, Inbox Credential Record, Active/Inactive status, and
  credential version to the DDD glossary.
- Record the system-scoped 60-minute sliding read-through directory in a new
  ADR. The cache scope and ownership choice is expensive to reverse.
- Document the source, commands, encryption boundary, key rotation runbook,
  deactivation order, TTLs, and errors in `docs/public-contract.md`.
- Remove instructions that ask Hosts to implement a custom credential store or
  reproduce Wappa's SQL schema.
- Explain why `WP_ACCESS_TOKEN` remains a legacy WhatsApp input and why hashing
  a bearer token would make it unusable.

## Open questions

None. Record fields, source ownership, mutation authority, TTLs, encryption,
key rotation, and deactivation are settled.

## Exit criteria

- Wappa ships the canonical WhatsApp active/inactive record union and encrypted
  envelope through supported public imports.
- Explicit mode accepts `IInboxDirectorySource` and offers no custom directory
  or credential-store replacement.
- `InboxDirectoryTable` works on every supported Table Cache backend under the
  exact System Scope.
- Wappa owns every cache mutation, index update, secret encryption, decryption,
  and Messenger/client eviction.
- Active, inactive, absent, and empty records follow their settled TTL rules.
- Version ordering and retry repair work under concurrency.
- Key rotation works for cache and durable Host records.
- The Host never needs plaintext after it calls Wappa's record service.
- Tests prove redaction and context-bound encryption.
- DDD, ADR, public-contract, environment, and migration docs match the code.
