---
version: 1.0.0
last_reviewed: 2026-08-30
status: done
author: sasha
urgency: high
owner: Wappa WhatsApp adapter and inbound runtime
blocked_by: encrypted Inbox Directory
decided_by: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
---

# Authenticated WhatsApp intake and WABA membership

## Context

The first v0.27 slice moved Inbox routing out of the callback URL and into the
WhatsApp payload. That is the right routing source only after Wappa authenticates
the exact bytes Meta sent.

The current candidate does not invoke a valid Meta POST signature check. Its
unused helper uses `WP_WEBHOOK_VERIFY_TOKEN`, which belongs to the GET challenge,
not POST HMAC authentication. The candidate also validates that a phone number
is active but does not prove it belongs to the WABA in `entry[].id`.

This PRD closes both trust gaps and makes account-scoped fan-out a cached,
qualified directory operation.

## Code reality

Already present:

- Canonical GET and POST path `/webhook/inboxes/whatsapp`.
- Batch splitting by Meta `entry` and `change`.
- Phone extraction from `value.metadata.phone_number_id` and flat
  `value.phone_number_id`.
- Rejection when the two phone fields disagree.
- WABA-only fan-out with duplicate removal and deterministic sorting.
- All contexts are built before scheduling starts.
- The old per-Inbox path returns 404.

Blocking defects:

- POST requests can reach parsing and routing without
  `X-Hub-Signature-256`.
- The existing signature helper uses the callback verify token as its HMAC
  secret.
- Non-object JSON roots can become 503 through an `AttributeError`.
- A phone-scoped change under the wrong `entry[].id` may pass.
- Account lookup is a bare string and can collide across Platforms.
- The account index has no settled freshness, atomicity, or stale-member repair
  contract.

## Scope

- Define one immutable `MetaApplicationConfig` per Wappa application.
- Authenticate POST callbacks with raw-body HMAC-SHA256 before parsing.
- Keep GET challenge verification separate.
- Route every phone-scoped change through qualified Inbox identity.
- Build and use the cached Platform Account reverse index.
- Prove Inbox-to-WABA membership for phone-scoped changes.
- Fail closed for unknown, inactive, empty, mismatched, or unavailable routing.
- Preserve all-or-nothing batch admission.
- Update ADR-0010 to record authenticated payload routing and membership.

## Out of scope

- Supporting several Meta Apps inside one Wappa application.
- Trying every App Secret in a global key ring.
- Platform webhook implementations other than WhatsApp.
- Exactly-once processing or a generic delivery fingerprint.
- Host business authorization.
- Per-Inbox App Secrets.

## Meta application configuration

Wappa owns this immutable application value:

```python
class MetaApplicationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_secret: SecretStr
    whatsapp_webhook_verify_token: SecretStr
    graph_api_version: str
    graph_base_url: AnyHttpUrl
```

Exactly one configuration source may be active:

- an explicit `MetaApplicationConfig` supplied during Wappa construction; or
- Wappa's environment adapter.

If both are present, startup fails. There is no silent precedence.

Environment mapping:

| Variable | Meaning |
| --- | --- |
| `META_APP_SECRET` | One Meta App's HMAC secret for POST callbacks |
| `WP_WEBHOOK_VERIFY_TOKEN` | Shared value for the GET challenge |
| `META_API_VERSION` | Graph API version used by Wappa |
| `META_BASE_URL` | Graph API base URL used by Wappa |

`META_APP_SECRET` is application-scoped. It never enters an Inbox credential
record and `SYSTEM_TOKEN_ENC_KEY` does not encrypt it.

Mounting the callback requires both callback secrets in every environment.
An outbound-only application that does not mount the callback does not need
them. There is no development bypass.

## POST authentication order

For every WhatsApp POST callback:

1. Read the exact request body bytes once.
2. Require one well-formed `X-Hub-Signature-256` header using the `sha256=`
   scheme.
3. Compute HMAC-SHA256 with `MetaApplicationConfig.app_secret`.
4. Compare the received and expected digests in constant time.
5. Return a generic 401 on missing, malformed, or mismatched signatures.
6. Only after success, decode JSON and require an object root.
7. Split, route, resolve directory records, prove membership, and build every
   Dispatch Context.
8. Schedule the accepted deliveries.

Before step 5 succeeds, Wappa must not parse JSON, query the directory, create
work, or log payload data. Error messages must not reveal which part of the
signature failed.

GET verification compares `hub.verify_token` against
`whatsapp_webhook_verify_token` and returns the challenge. It does not use
`META_APP_SECRET`, resolve an Inbox, or read the directory.

## Platform Account reverse index

The Host source returns records:

```python
await source.list_inboxes_for_platform_account(
    PlatformAccountRef(platform=WHATSAPP, platform_account_id=waba_id)
)
```

Wappa validates those records and projects active members into a typed Table
Cache row under System Scope.

```python
class PlatformAccountActiveIndexRecord(BaseModel):
    status: Literal["active"]
    account_ref: PlatformAccountRef
    inbox_refs: tuple[InboxRef, ...]
    index_version: int
    refreshed_at: datetime


class PlatformAccountEmptyIndexRecord(BaseModel):
    status: Literal["empty"]
    account_ref: PlatformAccountRef
    index_version: int
    checked_at: datetime
```

The active member tuple is sorted and duplicate-free. The conceptual storage
is:

```text
context_id = "__system__"
table      = "wappa_inbox_directory_account_index"
pkid       = PlatformAccountRef.cache_namespace
```

Use the Table Cache's atomic create/replace operations and `index_version` for
compare-and-set updates. On contention, retry a bounded number of times. Do not
add a Redis Set or a directory-specific Redis adapter.

## Membership rules

The reverse index is a projection, not authority. For every listed member,
Wappa resolves its primary directory record and checks:

- the record is active;
- its `InboxRef` matches the index member; and
- its `PlatformAccountRef` matches the requested WABA.

If a listed member is absent, inactive, or points to another WABA, Wappa performs
one synchronous source reload and repairs the index. If repair fails, intake
returns 503 and dispatches none of the batch. Wappa never dispatches the valid
subset.

A missing member cannot always be detected from a valid cached index. The Host
must call `refresh_inbox` after onboarding, rotation, WABA reassignment, or
deactivation. A Host outbox or reconciler may retry that same command.

Every phone-scoped change must prove that the resolved active Inbox belongs to
the `entry[].id` WABA. Existence alone is insufficient. A mismatch rejects the
whole callback as 400 before any Dispatch Context exists.

WABA-only changes fan out to every active validated member. Wappa never chooses
the first member and never uses the WABA ID as an Inbox ID.

## Empty and unavailable lookup

A successful source lookup with zero active members creates an empty index with
a fixed 60-minute TTL and returns 400 for the authenticated payload. Reads do
not renew that empty TTL.

If Redis or the source is unavailable, return 503. Do not cache an empty or
absent result from a failed dependency call.

An active index uses the directory's 60-minute sliding TTL and renews on each
successful validated hit.

## Batch admission

The accepted algorithm remains two-phase:

```text
authenticate exact body
  -> validate object JSON
  -> split every entry/change
  -> resolve every InboxRef
  -> prove every membership relation
  -> build every Dispatch Context
  -> schedule all deliveries
```

If item N fails, items 1 through N minus 1 are not scheduled. Preserve the
current build-all-before-schedule structure or replace it with an equivalent
admission object that tests can observe.

Wappa provides at-least-once delivery. Meta retries, batch splitting, and WABA
fan-out can repeat work. Host handlers remain responsible for idempotent side
effects based on Platform identifiers where available.

## Proposed module ownership

- API route: reads bytes and delegates; it does not parse provider identity.
- Meta callback authenticator: validates raw bytes and signature.
- WhatsApp routing module: understands Meta payload shapes and maps native IDs
  to Wappa references.
- Inbox Directory service: resolves primary records and account indexes.
- Inbound Runtime: creates Dispatch Contexts and schedules only accepted
  batches.

Do not let the API route know Table Cache names, encryption keys, token values,
or Host database queries.

## Failure contract

| Condition | Status |
| --- | ---: |
| Missing, malformed, or invalid Meta POST signature | 401 |
| Invalid GET verify token | 403 |
| Malformed JSON or non-object root | 400 |
| Conflicting phone identity fields | 400 |
| Confirmed unknown or inactive payload Inbox | 400 |
| Inbox and WABA membership mismatch | 400 |
| Confirmed WABA with no active Inboxes | 400 |
| Unsupported or unroutable authenticated shape | 400 |
| Directory, cache, source, or credential dependency unavailable | 503 |
| Unexpected Wappa defect | 500 |

Do not map an authenticated unknown payload Inbox to 401. Authentication has
already succeeded.

## Verification

Tests must cover:

- Exact raw bytes, including whitespace, are the HMAC input.
- Valid signature acceptance.
- Missing, malformed, wrong-algorithm, short, and mismatched signatures return
  the same generic 401.
- No JSON parsing, directory call, or work scheduling happens before HMAC
  acceptance.
- Callback startup fails without the App Secret or GET verify token.
- Outbound-only construction does not require callback secrets.
- Explicit and environment Meta configuration cannot coexist.
- GET verification remains separate and does not read the directory.
- Two phone-scoped changes under one WABA route to distinct Inboxes.
- The same raw Inbox ID on another Platform cannot satisfy WhatsApp routing.
- Phone-to-WABA mismatch fails 400 with no scheduled work.
- WABA fan-out covers zero, one, duplicate, and several source members.
- Stale, inactive, missing, and wrong-account index members trigger one repair.
- Repair failure returns 503 rather than dispatching a subset.
- Active index hits renew TTL; empty index hits do not.
- Mixed valid/invalid batches schedule nothing.
- Old per-Inbox GET and POST callback paths remain 404.

## Documentation obligations

- Amend ADR-0010 with raw-body authentication, one Meta App, qualified routing,
  WABA membership, and the final status matrix.
- Document `MetaApplicationConfig` and environment mapping in the public
  contract.
- Explain the Platform Account index, source repair, TTL, and Host refresh duty.
- Remove any statement that the callback payload is trusted merely because it
  came through the public route.
- Update deployment docs with the new callback URL and two-step rollback.

## Open questions

None. The one-Meta-App boundary, secret sources, HMAC order, account lookup,
membership, index repair, and empty-account behavior are settled.

## Exit criteria

- Every mounted WhatsApp POST callback verifies Meta HMAC before parsing.
- Wappa has exactly one Meta Application Configuration per application.
- `WP_WEBHOOK_VERIFY_TOKEN` is used only for GET verification.
- Phone-scoped payloads prove Inbox-to-WABA membership.
- WABA-only payloads use the Wappa-owned qualified reverse index.
- Empty, stale, unavailable, and mismatched account states follow the settled
  failure rules.
- Batch admission remains all-or-nothing before scheduling.
- Tests prove no unauthenticated request can reach directory or dispatch work.
- ADR, public contract, examples, and deployment docs match the code.
