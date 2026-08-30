---
version: 1.0.0
last_reviewed: 2026-08-30
status: implemented_awaiting_release_approval
author: sasha
candidate_version: 0.27.0
decision_record: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
release_blocked_by: all Wappa PRDs, PyPI publication, and Symphonai adoption
---

# Wappa v0.27.0 multi-Inbox release plan

## Outcome

Wappa v0.27.0 must let one Host Application run many WhatsApp Inboxes under
one Meta App without treating `WP_PHONE_ID`, `WP_BID`, or `WP_ACCESS_TOKEN` as
application-wide runtime identity.

The Host Application owns its durable Inbox schema. Wappa owns the canonical
credential record, encryption, system-scoped Inbox Directory, payload routing,
Platform Account membership checks, HTTP Inbox selection, and per-Inbox runtime
construction.

Legacy single-Inbox applications remain supported through an explicit legacy
mode. Legacy and explicit mode never fall back to each other.

## Why this directory is in progress

The first implementation slice exists in the current worktree. It changed the
WhatsApp callback to `/webhook/inboxes/whatsapp`, added payload routing and
WABA fan-out, introduced an explicit credential-store mode, added
`X-Wappa-Inbox-ID`, and expanded tests. The historical PRD and implementation
report now live under [`reports/`](./reports/).

That slice is evidence, not the finished v0.27 design. The 2026-08-29 review
found gaps that block release:

- POST callback authentication does not verify Meta's raw-body HMAC with
  `META_APP_SECRET`.
- The custom `IInboxCredentialStore` remains a Host extension and its database
  adapter dictates a SQL shape. The settled contract requires Wappa's mandatory
  `InboxDirectoryTable` plus a read-only Host source.
- Credentials can remain plaintext in cache and have no Wappa-owned rotation
  protocol.
- Identity uses an unqualified `inbox_id`; the settled global identity is
  `InboxRef(platform, inbox_id)`.
- Phone-scoped payloads do not prove that the Inbox belongs to `entry[].id`.
- Warm cache records can keep a deactivated Inbox active until expiry unless a
  caller remembers to invalidate them.
- `auto` routing and mixed configuration precedence remain in code. The settled
  modes are `legacy` and `explicit` only.
- Inbox middleware still applies one broad rule to `/api/whatsapp/*`; the
  settled design attaches Inbox requirements to route capabilities.
- Several errors still map to the wrong HTTP status, including non-object JSON
  roots and credential failures during Messenger construction.

Do not mark a PRD done because the first slice contains similarly named code.
Each PRD's exit criteria describe the accepted contract.

## Fixed design constraints

These decisions came from the grilling session and may not drift during
implementation:

1. `InboxRef(platform, inbox_id)` is the global runtime identity. The raw
   `inbox_id` only has uniqueness inside one Platform.
2. `PlatformAccountRef(platform, platform_account_id)` identifies a Platform
   Account. For WhatsApp, this is a WABA.
3. `InboxDirectoryTable` is a concrete Wappa component. Hosts cannot replace
   its model, cache shape, TTL rules, indexes, or mutation behavior.
4. A Host in explicit mode implements only `IInboxDirectorySource`, a
   read-only adapter from its durable schema to Wappa's canonical records.
5. The directory reuses `ITableCache` with
   `context_id=SYSTEM_SCOPE`, where `SYSTEM_SCOPE == "__system__"`.
6. The Table Cache constructor parameter becomes `context_id`. This rename
   does not change existing key values. Other cache families remain
   Inbox-scoped and keep `inbox_id`.
7. Active primary records and active account indexes have a 60-minute sliding
   TTL. Inactive, absent, and empty-account records have a fixed 60-minute TTL.
8. Wappa encrypts credential values with `SYSTEM_TOKEN_ENC_KEY`. Hosts persist
   Wappa's encrypted envelope and never decrypt it.
9. One Wappa application binds to one Meta App configuration. It may serve many
   WABAs and Inboxes under that Meta App.
10. Wappa authenticates the exact raw callback body before JSON parsing,
    directory reads, or background scheduling.
11. `X-Wappa-Inbox-ID` selects an Inbox Execution Context. Host authentication
    and authorization decide whether the caller may use it.
12. Webhook intake validates every item and builds every Dispatch Context
    before scheduling any item from the batch.
13. v0.27 keeps at-least-once delivery and does not invent a generic webhook
    fingerprint.
14. Wappa keeps `db` and `db_read` as optional session factories. The Inbox
    Directory source uses the primary path by default.

## PRD inventory

| Order | PRD | Owner | Status | Blocks v0.27 |
| ---: | --- | --- | --- | --- |
| 1 | [Runtime identity and Table Cache scope](./wappa/260829-high-runtime-identity-and-table-cache-scope.md) | Wappa domain and persistence | done | yes |
| 2 | [Encrypted Inbox Directory](./wappa/260829-high-encrypted-inbox-directory.md) | Wappa domain, security, and persistence | done | yes |
| 3 | [Authenticated WhatsApp intake and WABA membership](./wappa/260829-high-authenticated-whatsapp-intake.md) | Wappa WhatsApp and inbound runtime | done | yes |
| 4 | [Inbox-scoped HTTP execution and routing modes](./wappa/260829-high-inbox-http-and-routing-modes.md) | Wappa API and application builder | done | yes |
| 5 | [Failure semantics and release verification](./wappa/260829-high-failure-semantics-and-release-verification.md) | Wappa runtime and tests | done | yes |
| 6 | [DDD, public contract, migration, and release](./wappa/260829-high-docs-migration-and-release.md) | Wappa documentation and release | implemented; tag + PyPI publication await operator approval | yes |
| 7 | [Symphonai adoption](./symphonai/260829-high-symphonai-wappa-v0.27-adoption.md) | Symphonai | pending | yes, for series deletion |

`done` means the PRD's exit criteria are met in the worktree and verified by
the release report under [`reports/`](./reports/). PRD 6 is implemented up to
the operator-gated external actions (Git tag, PyPI publication, Meta callback
cutover), which are recorded there as pending approval.

## Dependency graph

```text
1. Runtime identity and Table Cache scope
   ├──> 2. Encrypted Inbox Directory
   │      ├──> 3. Authenticated intake and WABA membership
   │      └──> 4. HTTP execution and routing modes
   └───────────────────────────────────────────────┘
                            │
                            v
             5. Failure semantics and verification
                            │
                            v
               6. Docs, migration, and release
                            │
                            v
                  publish Wappa v0.27.0
                            │
                            v
                   7. Symphonai adoption
```

Implementation may overlap where files do not conflict. Contract decisions
still follow this order. In particular, do not cement the directory schema or
cache keys before `InboxRef`, `PlatformAccountRef`, and `context_id` exist.

## Decision traceability

| Grilling section | Settled topic | Implemented by |
| --- | --- | --- |
| 1 | Mandatory directory, Host source, System Scope, Table Cache naming | PRDs 1 and 2 |
| 2 | Credential record, Platform union, identity uniqueness, encryption and rotation | PRDs 1 and 2 |
| 3 | Redis read-through behavior, TTL, write order, refresh and deactivation | PRD 2 |
| 4 | Qualified WABA reverse lookup, index repair, membership and empty results | PRDs 2 and 3 |
| 5 | One Meta App, configuration ownership, HMAC and no bypass | PRD 3 |
| 6 | Complete WhatsApp HTTP operation matrix and Inbox Execution Context | PRD 4 |
| 7 | Legacy and explicit coexistence with no `auto` mode | PRD 4 |
| 8 | `db` and `db_read` contract plus separately deferred hardening | PRD 5 |
| 9 | Typed failures, status mapping and atomic intake | PRD 5 |
| 10 | Platform language, module ownership, release boundary and Symphonai work | PRDs 1 through 7 |

## Already implemented

The uncommitted candidate built on commit `bae8470`, the v0.26.3 release. The
historical report records clean Ruff, formatting, mypy, 576 tests, and
`git diff --check` at the time it was written. Those results apply to that
earlier candidate, not the finished PRD series.

Implemented pieces worth keeping and adapting:

- One WhatsApp callback path at `/webhook/inboxes/whatsapp`; the old
  per-Inbox callback returns 404.
- Payload splitting by `entry` and `change`.
- Extraction of `metadata.phone_number_id` and flat `phone_number_id`.
- Sorted, duplicate-free WABA fan-out.
- Build-all-before-schedule behavior in `accept_webhook_batch`.
- Per-delivery Messenger, cache, handler, and User context construction.
- `IIdentityResolver.resolve(..., inbox_id=...)`.
- `X-Wappa-Inbox-ID` parsing, format checks, existence checks, and context reset.
- A DB-only boot path and a preliminary explicit routing mode.
- Messenger invalidation hooks after credential rotation.
- Tests for two-Inbox routing, fan-out, header failures, context leakage, and
  removal of the old route.
- Initial edits to DDD docs, examples, `.env.example`, changelog, candidate
  version, and lock file.
- Tag-triggered PyPI publication already exists in
  `.github/workflows/publish.yml`, with operator guidance in
  `.github/workflows/PUBLISHING.md`. The release PRD must validate and use it.

Implemented pieces that the PRDs replace:

- `IInboxCredentialStore` as a Host-defined public extension.
- `DatabaseInboxCredentialStore` and its prescribed `wappa_inboxes` SQL table.
- `get_inbox_ids_for_platform_account(str)` without Platform qualification.
- Plain credential values in the cache record.
- `auto` routing and warning-based precedence.
- `WP_WEBHOOK_VERIFY_TOKEN` used or described as a POST signature secret.
- Broad path-prefix middleware for Inbox-dependent API calls.
- `401` for an authenticated but unknown payload Inbox.

## Implementation order

### Phase A: settle identity and persistence contracts

Implement PRDs 1 and 2. Migrate existing payload-routing code to qualified
identity and route all credential reads through the Wappa-owned directory.
This phase also adds encryption and rotation before any explicit-mode host can
persist production tokens.

### Phase B: close inbound and outbound boundaries

Implement PRDs 3 and 4. Authenticate Meta POST callbacks, prove WABA
membership, resolve one Inbox Execution Context per HTTP request, and remove
configuration ambiguity.

### Phase C: make failures testable

Implement PRD 5. Add typed failures, exact HTTP mappings, all-or-nothing tests,
backend conformance tests, and security regression tests. Run the full suite
after every contract migration, not only at the end.

### Phase D: publish the contract

Finish PRD 6. Update all DDD and public-contract documents, migration notes,
examples, changelog, version metadata, and generated templates. Create the Git
tag and let the GitHub release workflow publish v0.27.0 to PyPI. Verify the
published artifact; a local wheel or editable install does not count.

### Phase E: adopt in Symphonai

Implement PRD 7 against the published package. Symphonai owns its durable
schema, source adapter, Owner-scoped Table Cache helpers, migrations, and live
acceptance. Wappa must not absorb Owner language to make this easier.

## Resource budget

Keep file ownership narrow because the first candidate already changes many of
the same modules.

- Identity and persistence work owns `wappa/domain/inbox/`, Table Cache
  interfaces/adapters, and their tests.
- Security and directory work owns `wappa/core/security/`, directory services,
  canonical records, and directory conformance tests.
- Inbound work owns Meta configuration, webhook authentication, WhatsApp
  routing, membership, and Inbound Runtime admission.
- API work owns capability dependencies, Inbox Execution Context, route
  migration, and routing-mode construction.
- Documentation and release work starts after public names settle, though it
  may keep the glossary current during implementation.
- Symphonai implementation happens in its repository after the Wappa public
  contract and release artifact exist.

Use a second reviewer for raw-body authentication, credential encryption,
versioned directory mutation, and release publication. Those changes handle
secrets or irreversible external actions. Backend conformance tests should run
for every directory change; the full suite runs at each PRD boundary.

## Deferred work that does not block v0.27

Two decisions need separate backlog items outside this release series:

- PostgreSQL plugin hardening: enforced read-only transactions for `db_read`,
  replica cooldown and rotation, configurable primary fallback, and telemetry.
- Delivery identity: a provider-aware identity model for retries and WABA
  fan-out. v0.27 keeps at-least-once delivery without a generic fingerprint.

Do not add these as PRDs inside this directory. Backlog rules would make them
part of the release's deletion gate.

## Release gates

Wappa v0.27.0 cannot ship until:

- Every Wappa PRD has met its exit criteria.
- Ruff, formatting, mypy, the full pytest suite, and `git diff --check` pass on
  the release commit.
- The package builds from a clean checkout and its wheel contains the intended
  public modules and documentation metadata.
- `CHANGELOG.md` names the decisions from the grilling session, including
  qualified Inbox identity, the mandatory directory, encrypted credentials,
  Meta HMAC verification, WABA membership, routing modes, and migration breaks.
- The DDD glossary, architecture docs, ADRs, public contract, CLI templates,
  examples, and environment docs agree with the code.
- A GitHub tag for `v0.27.0` exists and the configured GitHub Actions release
  job publishes that exact version to PyPI.
- Installing `wappa==0.27.0` from PyPI succeeds in a clean environment and
  reports version `0.27.0`.

## Series deletion gate

Delete this entire directory only after all release gates pass and Symphonai
has completed its adoption PRD against the published PyPI package.

Symphonai acceptance must prove at least two active WhatsApp Inboxes under the
same Meta App can receive and send without Owner, Chat, cache, credential, or
sender crossover. It must also prove deactivation and token rotation reach the
runtime directory through Wappa's commands.

Git history is the archive. Do not create a `done/` copy.

## External actions and rollback

Changing the Meta callback URL, creating the Git tag, publishing to PyPI, and
deploying Symphonai affect systems outside this repository. Perform them only
when the release implementation has passed its gates and the operator has
approved the action.

The callback rollback is a two-part operation. Revert both the deployed Wappa
version and the Meta callback URL. Reverting only one stops webhook delivery.
