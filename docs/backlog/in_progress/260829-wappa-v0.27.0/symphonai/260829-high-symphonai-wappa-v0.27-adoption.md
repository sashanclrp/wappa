---
version: 1.0.0
last_reviewed: 2026-08-30
status: pending
author: sasha
urgency: high
owner: Symphonai backend and consumer integrations
blocked_by: published wappa 0.27.0
decided_by: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
---

# Symphonai adoption of Wappa v0.27.0

## Context

Symphonai needs System, Owner, and Inbox cache contexts without pushing Owner
into Wappa. It also needs one durable source of Inbox credentials, encrypted by
Wappa, that supports several Owners, WABAs, and phone numbers under one Meta App.

This PRD belongs to the v0.27 series because the backlog directory cannot be
deleted until Symphonai proves the published Wappa package works in its real
multi-Owner deployment. The code changes occur in the Symphonai repository.

## Dependency rule

Implement final acceptance against `wappa==0.27.0` installed from PyPI.

Symphonai may use a local editable Wappa checkout during development, but that
does not close any release or adoption gate. Record the switch to the published
package and remove local path overrides before acceptance.

## Wappa and Symphonai ownership

Wappa owns:

- `InboxRef` and `PlatformAccountRef`;
- canonical credential records and encrypted envelopes;
- encryption, decryption, key rotation, and redaction;
- `InboxDirectoryTable`, System Scope, TTLs, indexes, and mutation commands;
- payload routing, WABA membership, Messenger construction, and HTTP Inbox
  selection; and
- the `context_id` Table Cache contract.

Symphonai owns:

- Owner, Owner Channel, Chat, Conversation, and Message invariants;
- its PostgreSQL schema and migrations;
- mapping database rows to Wappa records;
- caller authorization for an Owner or Inbox;
- which Table Cache data belongs to System, Owner, or Inbox scope;
- business transaction timing and optional outbox delivery; and
- deployment, Meta callback cutover, and live multi-Owner acceptance.

Symphonai must not implement a custom Inbox Directory, write raw Wappa Redis
rows, choose its own TTLs, decrypt access tokens, or reproduce Wappa's internal
index format.

## Scope

- Upgrade the dependency to published Wappa v0.27.0.
- Add or adapt durable Inbox credential storage in Symphonai.
- Persist Wappa's encrypted canonical records.
- Implement `IInboxDirectorySource` using the primary database path.
- Wire explicit Inbox Routing Mode and System encryption settings.
- Replace local global Table Cache workarounds with Wappa's System Scope helper.
- Add an Owner-scoped Table Cache builder owned by Symphonai.
- Audit every `VersionedTableCache` and `ITableCache` construction.
- Send `X-Wappa-Inbox-ID` for every Inbox-dependent Wappa HTTP request.
- Preserve one process environment declaration of `META_APP_SECRET`.
- Update callback configuration and run two-Inbox acceptance.

## Out of scope

- Adding Owner to Wappa.
- Changing User, expiry, state, SSE, or other Wappa caches to Owner scope.
- Supporting several Meta Apps in one Symphonai Wappa application.
- Implementing the deferred PostgreSQL replica hardening inside this adoption.
- Letting Symphonai choose a different directory record schema.

## Three Table Cache contexts

Symphonai will use Table Cache at these independent scopes:

| Context | `context_id` | Example data |
| --- | --- | --- |
| System | `SYSTEM_SCOPE`, exact value `"__system__"` | Wappa Inbox Directory and global application settings |
| Owner | Symphonai `owner_id` | Owner component configuration and Owner-wide cached DB records |
| Inbox | Wappa Inbox namespace | conversation or integration data that differs by Platform Inbox |

These are not a hierarchy. Symphonai chooses the correct scope at each call
site.

Suppose one person contacts the same Owner through WhatsApp and Instagram.
Owner-scoped configuration may be shared, while conversation state remains
different because each Platform Inbox has a distinct `InboxRef`.

Only Table Cache accepts these general contexts. `UserCache`, `ExpiryCache`,
State Handler, PubSub, SSE, and other Wappa runtime caches remain scoped by
Inbox. Do not pass Owner ID or System Scope into them.

## Table Cache migration

Replace Symphonai's local `SYSTEM_SCOPE` and `build_global_table_cache()`
workaround with Wappa's exported constant and system-table builder.

Create a Symphonai-owned Owner builder that passes:

```python
context_id=str(owner_id)
```

Keep ordinary Inbox builders passing Wappa's encoded Inbox namespace as
`context_id`.

Audit every direct and wrapped construction, including
`VersionedTableCache`. Classify each table by the invariant of its data, not by
the request that happens to read it.

The `inbox_id` to `context_id` constructor change requires keyword edits only.
It does not require Redis data migration when the value stays the same. Tests
must compare representative old and new keys before deployment.

## Durable credential storage

Symphonai chooses its own table and columns. The durable model must preserve all
fields needed to reconstruct Wappa's canonical record, including:

- schema and Platform discriminator;
- native Inbox ID and Platform Account ID;
- active/inactive status;
- encrypted credential envelope;
- monotonic credential version; and
- timezone-aware update evidence.

Do not store a hash of the access token. Meta requires the original bearer value
for outbound calls. Wappa's encrypted envelope provides reversible protection.

### Onboarding

1. Symphonai authorizes the business action and gathers the plaintext token.
2. Call Wappa's credential creation service with `SecretStr` and qualified
   identity.
3. Receive the validated record with encrypted envelope.
4. Persist that exact record within the Symphonai business transaction.
5. Commit.
6. Call Wappa `refresh_inbox(inbox_ref)`.
7. If refresh fails, surface the operational failure and retry through the
   selected job/outbox mechanism. Never write Redis directly.

### Rotation

Increment `credential_version` across the whole lifetime of the Inbox. Call
Wappa with the new plaintext token, persist the returned encrypted record,
commit, then refresh. Equal versions may only repeat an identical record.

### Deactivation

Persist Wappa's inactive record with a higher version and no access token.
Commit, then call the Wappa deactivation/refresh command. Acceptance must prove
the Inbox leaves the WABA index and can no longer send or receive through the
runtime directory.

### Encryption-key rotation

Symphonai supplies the active `SYSTEM_TOKEN_ENC_KEY` and any temporary
`SYSTEM_TOKEN_ENC_PREVIOUS_KEYS` to the Wappa process. For durable migration:

1. Enumerate Symphonai credential records.
2. Call Wappa `rotate_encrypted_record(record)` for each.
3. Persist the returned envelope without decrypting it.
4. Deploy all instances with the active and previous keys.
5. Wait through the directory TTL and deployment overlap.
6. Remove previous keys only after every durable row uses the active key.

Document recovery consequences. If every accepted key is lost, Symphonai must
obtain new Platform credentials.

## Directory source adapter

Implement Wappa's read-only source protocol:

```python
async def get_inbox(inbox_ref: InboxRef) -> InboxCredentialRecord | None: ...

async def list_inboxes_for_platform_account(
    account_ref: PlatformAccountRef,
) -> tuple[InboxCredentialRecord, ...]: ...
```

The adapter queries Symphonai's primary database by default and maps rows to the
Wappa model. It returns encrypted records untouched. It must include Platform in
both lookups and never treat raw IDs as globally unique.

The account lookup returns every matching record needed for Wappa to validate
activity and build its reverse index. Do not pre-build Redis keys or return only
Inbox IDs.

Add query-count tests. A warm Wappa directory hit should make no database call;
a cold primary lookup should make one source call for the requested operation.

## Configuration

Select:

```text
WAPPA_INBOX_ROUTING=explicit
SYSTEM_TOKEN_ENC_KEY=...
SYSTEM_TOKEN_ENC_PREVIOUS_KEYS=...  # only during rotation
META_APP_SECRET=...
WP_WEBHOOK_VERIFY_TOKEN=...
```

Use the actual Wappa routing variable name implemented by v0.27 if it differs
from the illustrative `WAPPA_INBOX_ROUTING` name above. The final migration
guide is authoritative.

Remove these legacy Inbox variables from explicit deployments:

```text
WP_ACCESS_TOKEN
WP_PHONE_ID
WP_BID
```

Symphonai already uses `META_APP_SECRET` for the Meta Marketing API. Declare it
once in the process environment. Wappa's environment adapter reads the same
variable directly.

Do not:

- add a second Wappa-specific App Secret variable;
- copy the value through a Symphonai settings alias solely for Wappa;
- pass explicit `MetaApplicationConfig` while Wappa's environment-backed Meta
  configuration is active; or
- move `META_APP_ID` and `META_ADS_CONFIG_ID` into Wappa settings.

Symphonai's existing Marketing API settings may keep reading
`META_APP_SECRET`, `META_APP_ID`, and `META_ADS_CONFIG_ID`. Wappa consumes only
the settings its contract declares.

## HTTP and authorization migration

Every Symphonai call to an Inbox-dependent Wappa HTTP operation sends:

```text
X-Wappa-Inbox-ID: <native Inbox ID for the WhatsApp route>
```

Symphonai must authorize the caller against Owner Channel or its equivalent
before proxying or issuing the request. The header is not proof of permission.

Audit sends and services:

- text, receipts, media, interactive, contact, location, and Templates;
- media upload, metadata lookup, download, and delete;
- Template lookup, listing, and namespace;
- State Handler operations; and
- Inbox-specific WhatsApp health.

Local validation, static limits, root health, docs, and OpenAPI need no header.

Template callers stop supplying a WABA separately. Wappa resolves it from the
selected Inbox record.

## Business-context propagation

Inbound handler work receives qualified Inbox identity from Wappa. Symphonai
then resolves:

```text
InboxRef
  -> Owner Channel
  -> Owner
  -> Chat
  -> Conversation and Message
```

Queries and uniqueness constraints must keep the same person's chats separate
when they write through distinct Inboxes, including two Platforms under one
Owner. Wappa supplies identity and runtime scope; Symphonai enforces Owner and
Chat rules.

Outbound commands start with an authorized Owner Channel or equivalent durable
relation, derive one `InboxRef`, and pass that exact Inbox into Wappa. Do not use
an environment default or choose the first active channel.

## Tests

### Unit and integration

- Durable row mapping to active and inactive Wappa records.
- Platform-qualified source lookups.
- Source uses primary database sessions for security-sensitive reads.
- Onboarding, rotation, deactivation, retry, stale version, and equal version.
- Key rotation without plaintext exposure.
- System, Owner, and Inbox Table Cache builders create the intended keys.
- Every `VersionedTableCache` call site has an explicit scope classification.
- Legacy variables cause explicit-mode startup failure.
- One `META_APP_SECRET` environment value feeds both Symphonai Marketing API
  settings and Wappa without duplicate configuration.
- All Inbox-dependent HTTP calls send the selected header after authorization.

### Live acceptance

Use at least two active WhatsApp Inboxes under the same Meta App. Prefer Inboxes
mapped to different Symphonai Owners because that exposes crossover.

Prove:

1. Meta GET verification and signed POST delivery work on the one callback.
2. A User can message Inbox A and Inbox B; each event resolves the correct Owner
   Channel, Owner, Chat, Conversation, and Message.
3. Replies leave from the same Inbox that received each conversation.
4. API text, media, location, Template, and media download use the selected
   Inbox credentials.
5. Cache, state, SSE, logs, and handler identity do not cross Inboxes.
6. A WABA-only event fans out to every expected Inbox and no unexpected Inbox.
7. A forged WABA/phone relation fails before handler work.
8. Deactivation removes one Inbox without disrupting the other.
9. Token rotation changes outbound credentials without restarting or leaking
   the token.
10. Redis eviction causes one database source load, then warm reads avoid the
    database while the sliding TTL renews.
11. Directory or source outage returns the documented failure and does not
    masquerade as an unknown Inbox.
12. Local Wappa validation and limits remain available during a directory
    outage.

Record logs with secrets redacted, request IDs, the qualified Inbox references,
and the resulting business records. Do not include message content unless the
acceptance environment permits it.

## Deployment and rollback

1. Deploy Symphonai with the durable records, source adapter, explicit mode,
   and new Wappa package before changing Meta's callback.
2. Verify health and directory warm-up.
3. Change the Meta callback to `/webhook/inboxes/whatsapp` and complete the GET
   challenge.
4. Run live acceptance for each Inbox.

Rollback needs both the prior Symphonai/Wappa deployment and prior Meta callback
URL. Preserve durable encrypted records and key access during rollback planning;
an older Wappa version may not understand them.

## Documentation obligations

Update Symphonai's architecture, domain glossary, environment docs, operational
runbook, deployment instructions, and developer examples. The Symphonai glossary
may define Owner and Owner Channel; Wappa docs must not.

Document which application components use System, Owner, and Inbox Table Cache
scope. Record why User and runtime state caches remain Inbox-scoped.

## Open questions

None at the Wappa contract level. Symphonai may choose its table names, migration
layout, and retry mechanism as long as it preserves Wappa's records and command
ordering.

## Exit criteria

- Symphonai installs `wappa==0.27.0` from PyPI with no editable/path override.
- Explicit mode starts with no legacy Inbox credential environment variables.
- Symphonai implements only the Wappa source port and uses Wappa's directory and
  credential commands unchanged.
- Durable credentials remain encrypted and Symphonai never decrypts them.
- System, Owner, and Inbox Table Cache contexts are implemented and audited.
- One `META_APP_SECRET` declaration serves the existing Marketing API settings
  and Wappa's environment adapter.
- Every Inbox-dependent Wappa HTTP call carries an authorized Inbox selection.
- Two-Inbox live acceptance proves inbound, outbound, business-record, cache,
  state, and sender isolation.
- Deactivation, rotation, cold-cache refill, WABA fan-out, and outage behavior
  pass acceptance.
- Symphonai DDD, architecture, environment, and operations docs match the
  deployed integration.
- Evidence is recorded in the Wappa series release/adoption report before the
  backlog directory is deleted.
