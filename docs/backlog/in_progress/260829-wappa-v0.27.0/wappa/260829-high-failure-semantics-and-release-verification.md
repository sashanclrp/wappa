---
version: 1.0.0
last_reviewed: 2026-08-30
status: done
author: sasha
urgency: high
owner: Wappa runtime and tests
blocked_by: runtime identity, Inbox Directory, authenticated intake, and HTTP context
decided_by: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
---

# Failure semantics and release verification

## Context

Multi-Inbox routing fails in meaningfully different ways. An unknown Inbox is a
bad selection. A directory outage is a dependency failure. An invalid Meta
signature is an authentication failure. Treating all three as `RuntimeError`,
401, or 500 makes incidents hard to diagnose and can make Meta retry the wrong
class of response.

The first v0.27 slice has useful regression tests and build-all-before-schedule
behavior, but its error mapping is incomplete. A non-object JSON root can become
503, unknown payload Inboxes return 401, and a credential failure during
Messenger construction can escape as 500.

This PRD defines typed domain failures, boundary mappings, Dispatch Context
database capabilities, and the test evidence required for release.

## Scope

- Add typed Inbox and directory failures.
- Map them consistently at webhook, API, programmatic, and background boundaries.
- Preserve all-or-nothing callback admission.
- Use one Dispatch Context builder across webhook, API-message, cron, and
  external-event paths.
- State the exact `db` and `db_read` contract v0.27 exposes.
- Add backend, security, concurrency, route, and migration regression tests.
- Remove dead or divergent runtime entry points when they have no public
  contract.

## Out of scope

- Exactly-once delivery.
- A generic delivery fingerprint.
- Enforced PostgreSQL read-only transactions, replica cooldown, fallback
  configuration, or replica telemetry.
- Database row-level security or Host business authorization.
- Replaying a query after a database session has been yielded.

## Typed failures

At minimum, define:

```python
class InboxNotFoundError(...): ...
class InboxMembershipError(...): ...
class InboxDirectoryUnavailableError(...): ...
class InboxCredentialIntegrityError(...): ...
```

Add a specific mutation/version conflict if the directory needs one. The public
base classes must let Host code catch stable categories without importing Redis,
Fernet, HTTP client, or SQL exceptions.

Rules:

- `InboxNotFoundError` means a healthy lookup confirmed unknown or inactive.
- `InboxMembershipError` means known identities contradict the required
  Platform Account relation.
- `InboxDirectoryUnavailableError` means Wappa could not determine the answer
  because cache, source, or another required directory dependency failed.
- `InboxCredentialIntegrityError` means the record or encrypted credential
  failed validation and Wappa cannot safely use it.
- Never catch every exception and report "unknown Inbox."
- Typed messages may include safe qualified identity. They must exclude tokens,
  ciphertext, keys, payloads, and source query details.

## HTTP status matrix

### WhatsApp callback

| Condition | Status |
| --- | ---: |
| Missing or invalid Meta HMAC | 401 |
| Invalid GET verify token | 403 |
| Malformed JSON or non-object root | 400 |
| Invalid Inbox identifier format in authenticated payload | 400 |
| Confirmed unknown or inactive payload Inbox | 400 |
| WABA membership mismatch | 400 |
| Confirmed WABA with no active members | 400 |
| Other structurally unroutable authenticated payload | 400 |
| Directory, Redis, source, decrypt, or required runtime dependency unavailable | 503 |
| Unexpected Wappa defect | 500 |

### Wappa HTTP operations

| Condition | Status |
| --- | ---: |
| Missing required Inbox selection | 400 |
| Malformed `X-Wappa-Inbox-ID` | 400 |
| Healthy directory confirms unknown or inactive selected Inbox | 404 |
| Directory, source, Redis, or decrypt failure | 503 |
| Host authentication or authorization failure | Auth plugin contract |
| Unexpected Wappa defect | 500 |

Programmatic entry points raise typed errors. They do not fabricate HTTP status
objects. Background delivery records the typed category when an HTTP response
can no longer report it.

## Atomic intake

One authenticated Meta POST is admitted as one batch:

1. Authenticate raw bytes.
2. Parse and validate an object root.
3. Split every entry/change.
4. Resolve every Inbox Reference.
5. Prove every WABA membership relation.
6. Translate every delivery and build every Dispatch Context.
7. Schedule the complete batch.

Failure before step 7 schedules no task. Tests need an observable tracker so
they can assert zero submissions when the final item fails.

Wappa keeps at-least-once semantics. Host handlers must tolerate Meta retries,
batch splitting, and WABA fan-out. Do not hash the payload or use batch position
as a supposedly stable identity; both can collapse legitimate events or change
when Meta repackages a callback.

## Dispatch Context consistency

Webhook, API-message, cron, and external-event paths use one builder for shared
runtime capabilities. The builder accepts qualified Inbox identity and supplies:

- Inbox and User identity where the event has a User;
- Messenger and Cache Factory when the path needs them;
- optional `db` and `db_read` factories;
- SSE/log identity; and
- a cloned `WappaEventHandler`.

Each background task binds its own context before handler work and resets it
afterward. Building several contexts in one request must not leave build-phase
logs attributed to the last item.

If the candidate's single-delivery `InboundRuntime.accept_webhook` has no caller
and no documented programmatic contract, delete it. A second intake path would
need the same authentication, routing, membership, and admission rules, which
the method cannot guarantee from one raw Inbox ID.

## `db` and `db_read` contract

Keep both public names:

- `db` is the Primary Session Factory. It supports writes and
  primary-consistent reads.
- `db_read` is the Read-Intent Session Factory. It promises eventual
  consistency and may use a replica or current plugin fallback behavior.

Both remain optional `SessionFactory | None`. Do not install a Null Object that
returns a fake session. A small `require_database()` helper may turn `None` into
one direct runtime error.

Wappa supplies sessions. It does not add Inbox predicates, Owner authorization,
PostgreSQL row-level security, or Host repository invariants. A Host that writes
and must read its write uses `db`, preferably in one transaction.

Credential-directory cache misses, refreshes, rotations, deactivations, and
reconciliation use the primary path by default. The source adapter owns that
choice because it owns the Host repository.

Do not claim `db_read` is database-enforced read-only in v0.27 unless the
separate PostgreSQL plugin hardening work lands. The current target for that
later PRD is:

- PostgreSQL read-only transactions on replica and primary fallback;
- read-only replica roles;
- `ReadFallbackPolicy.PRIMARY` or `ERROR`;
- replica rotation before a session is yielded, bounded cooldown, and health
  telemetry; and
- rollback/end on successful read sessions rather than normal commit.

Those improvements do not block v0.27 and do not belong in this implementation.

## Required test groups

### Identity and directory

- Cross-Platform raw ID collision.
- Active, inactive, absent, stale-version, equal-version, and recreated Inbox.
- Sliding and fixed TTLs.
- Source/cache outage and negative-cache prevention.
- Primary/index partial-write repair.
- Messenger/client eviction after refresh and deactivation.

### Credential security

- Encryption context binding and redaction.
- Active and previous keys.
- Cache rewrite and durable record re-encryption.
- Wrong key, corrupt envelope, copied ciphertext, and lost-key failures.

### Callback security and routing

- Raw-body HMAC ordering and generic signature failures.
- Object-root validation for `[]`, `null`, strings, numbers, and booleans.
- Phone routing, WABA fan-out, membership proof, stale-index repair, and empty
  account behavior.
- A mixed batch whose last change fails, with zero scheduled work.

### HTTP operations and modes

- Every row of the route capability matrix.
- One directory resolution per Inbox-dependent request.
- Local-only routes remain independent of directory health.
- Legacy and explicit startup matrix, including forbidden mixed settings.
- Context reset across sequential and concurrent requests.

### Dispatch and database

- Same context builder used by webhook, API-message, cron, and external events.
- `db` and `db_read` remain optional and preserve their public names.
- Missing factories produce a direct error rather than a fake session.
- Host repository calls receive no automatic Inbox or Owner filtering.

### Compatibility and release

- Old callback paths return 404.
- Existing WhatsApp cache keys remain usable where promised.
- Stale `ITableCache(inbox_id=...)` keywords fail with migration guidance.
- Public import tests cover every new supported model, enum, command, and error.
- CLI-generated projects use the v0.27 contracts.

## Verification commands

Run on the release commit:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy wappa
uv run pytest -q
git diff --check
uv build
```

Record the exact test count and artifact names in the final implementation
report. A prior run from the first candidate does not prove the final series.

Inspect the built wheel rather than assuming source files were packaged. Test a
clean install of that wheel before tagging.

## Observability checks

Health and logs must distinguish:

- selected routing mode;
- callback configuration readiness;
- directory unavailable versus Inbox absent;
- credential integrity failure without record contents; and
- background dispatch failure category.

Never expose plaintext tokens, encrypted envelopes, App Secrets, encryption
keys, callback payload bodies, or raw source exceptions.

## Open questions

None for v0.27. PostgreSQL read enforcement and delivery identity remain
separate backlog work and cannot delay this contract.

## Exit criteria

- All directory and credential failures use stable typed categories.
- Every HTTP boundary implements the agreed matrix.
- Messenger construction and other late dependency reads cannot turn a
  directory outage into an unclassified 500.
- Callback admission schedules no partial batch.
- All runtime entry points use one context builder or document why they require
  a different capability set.
- `db` and `db_read` match the stated v0.27 contract without claiming deferred
  PostgreSQL hardening.
- Dead intake paths are removed.
- The full test groups pass on every supported cache backend where applicable.
- Release verification runs against the final candidate and built artifact.
