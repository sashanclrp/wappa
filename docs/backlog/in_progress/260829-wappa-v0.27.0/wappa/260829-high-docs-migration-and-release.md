---
version: 1.0.0
last_reviewed: 2026-08-30
status: done
author: sasha
urgency: high
owner: Wappa documentation and release
blocked_by: all runtime PRDs
decided_by: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
---

# DDD, public contract, migration, and release

## Context

v0.27 changes identity, credential ownership, callback authentication, cache
scope, environment behavior, HTTP selection, and Host integration. Shipping the
code without updating every teaching path would recreate the old
`WP_PHONE_ID`-as-global-authority design in the next generated application.

The worktree already contains early edits to the glossary, architecture,
public contract, changelog, environment example, CLI example, version metadata,
and ADRs. Those edits describe the first candidate in places, including its
custom credential store and `auto` mode. They must be reconciled with the final
grilling decisions before release.

The repository already has a tag-triggered trusted-publishing workflow at
`.github/workflows/publish.yml` and setup instructions at
`.github/workflows/PUBLISHING.md`. This PRD validates and uses that path. It does
not add a second publication mechanism.

## Scope

- Make the DDD document graph agree with the implemented v0.27 contract.
- Record the hard-to-reverse decisions in ADRs.
- Rewrite the public contract and migration guide for Host implementers.
- Update README, environment examples, CLI templates, generated examples, and
  health documentation.
- Write a v0.27 changelog entry that names the decisions made in the grilling
  session.
- Build, tag, publish, and verify Wappa v0.27.0 through the repository's GitHub
  release workflow.
- Preserve the first candidate PRD and implementation report under `reports/`
  as implementation evidence while the series remains active.

## Out of scope

- Archiving completed backlog files in a `done/` directory.
- Publishing deferred PostgreSQL plugin or delivery-identity behavior as part
  of v0.27.
- Performing Symphonai code changes in the Wappa repository.
- Claiming other Platforms are implemented because the credential union can
  grow later.

## Documentation graph

### Root glossary

`CONTEXT.md` must define, without implementation detail:

- Platform and Platform Account;
- Inbox, `inbox_id`, Inbox Reference, and qualified uniqueness;
- Platform Account Reference;
- Inbox Routing Mode;
- Inbox Credential Record and active/inactive status;
- Inbox Directory;
- Inbox Execution Context and Dispatch Context;
- Meta Application Configuration;
- Primary Session Factory and Read-Intent Session Factory; and
- Host Application boundaries, including the fact that Owner is not Wappa
  language.

Remove or correct terms that imply a raw Inbox ID is globally unique. Use
Platform consistently except for established Payment Provider and Meta Tech
Provider phrases.

### Context map and architecture

Update root and nearest module architecture docs to show this dependency
direction:

```text
Host durable schema
  -> IInboxDirectorySource
  -> Wappa directory services
  -> InboxDirectoryTable on ITableCache
  -> internal credential resolver
  -> WhatsApp client/Messenger construction
```

Document module ownership under `wappa/domain/inbox/`,
`wappa/core/security/`, persistence, WhatsApp adapter, inbound runtime, and API.
The API cannot own payload parsing, cache names, encryption, or source queries.

Update persistence architecture for `context_id`, System Scope, backend reuse,
and the limit that only Table Cache accepts non-Inbox contexts.

### ADRs

Amend ADR-0010 so it records:

- one callback path;
- authenticated raw-body payload routing;
- `InboxRef` and `PlatformAccountRef`;
- phone-to-WABA membership proof;
- deterministic WABA fan-out;
- all-or-nothing admission; and
- the removal of URL Inbox authority.

Add one ADR for the Inbox Directory because these decisions are expensive to
reverse and came from real alternatives:

- Wappa-owned concrete directory;
- Host-owned durable schema through one read-only source;
- `ITableCache` reuse under `SYSTEM_SCOPE = "__system__"`;
- 60-minute sliding active TTL and fixed negative TTL;
- Wappa-only mutation commands; and
- encrypted canonical records.

Superseded ADRs keep their historical statement and link to the replacing
decision. Do not rewrite history as if the old decision never existed.

### Public contract

`docs/public-contract.md` must document supported imports and runtime behavior:

- identity models and cache namespace encoding;
- Table Cache `context_id` rename and compatibility;
- canonical active/inactive WhatsApp credential records;
- encrypted envelope, key variables, rotation runbook, and redaction boundary;
- `IInboxDirectorySource` and Wappa-owned commands;
- directory TTL, version, repair, and deactivation rules;
- Meta Application Configuration and POST/GET authentication split;
- Platform Account reverse lookup and membership;
- `X-Wappa-Inbox-ID` route matrix and authorization warning;
- legacy/explicit configuration matrix;
- typed errors and HTTP mappings;
- at-least-once delivery and Host idempotency duty;
- `db` and `db_read` guarantees and limits; and
- callback cutover and rollback.

Every public code sample must import only supported paths and pass type checks.

## Host migration guide

Write one ordered guide with separate paths.

### Legacy single-Inbox Host

1. Keep `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, and `WP_BID` as one complete bundle.
2. Select or inherit `InboxRoutingMode.LEGACY`.
3. Add callback-level Meta settings when mounting the callback.
4. Change the Meta callback URL to `/webhook/inboxes/whatsapp`.
5. Update any `ITableCache(inbox_id=...)` keyword to `context_id=...`.
6. Verify inbound and outbound traffic through the one configured Inbox.

### Explicit multi-Inbox Host

1. Remove `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, and `WP_BID` from the process
   environment.
2. Set `InboxRoutingMode.EXPLICIT` and configure `SYSTEM_TOKEN_ENC_KEY`.
3. Implement `IInboxDirectorySource` against the Host's own durable schema.
4. Use Wappa's credential service to create encrypted records before database
   persistence.
5. Call `refresh_inbox` after committed onboarding, rotation, reassignment, and
   deactivation.
6. Send `X-Wappa-Inbox-ID` on every Inbox-dependent Wappa HTTP operation.
7. Configure one Meta App Secret and callback verify token.
8. Test WABA fan-out, membership mismatch, cache miss, deactivation, rotation,
   dependency outage, and two-Inbox isolation.

Make clear that `WP_ACCESS_TOKEN` is valid only in legacy mode. Explicit mode
stores one encrypted bearer credential per Inbox record, even when several
records contain the same physical token value.

## Examples and templates

Audit and update:

- root README and quick start;
- `.env.example`;
- every CLI project template;
- Railway and other deployment guides;
- callback URL helpers and startup output;
- OpenAPI examples;
- custom credential-store examples;
- Table Cache construction examples;
- media, Template, state, and send request examples; and
- health response examples.

Generated examples must offer one clear legacy path and one explicit path. Do
not mix variables from both in one `.env` block.

Remove `/send-complex-buttons` and `/send-menu-list` from HTTP examples that
present them as production endpoints. The underlying message examples may stay
as client or Messenger demonstrations.

## Changelog requirements

The `0.27.0` entry must link to or name the grilling session and state:

- Inbox identity is qualified by Platform.
- The one callback URL derives Inbox identity from an authenticated payload.
- Wappa verifies Meta HMAC with `META_APP_SECRET` before parsing.
- Wappa proves phone-to-WABA membership and owns the cached reverse index.
- Explicit mode uses the mandatory encrypted Inbox Directory and Host source.
- `SYSTEM_TOKEN_ENC_KEY` and previous-key rotation protect stored credentials.
- Table Cache construction uses `context_id`; other caches remain Inbox-scoped.
- `X-Wappa-Inbox-ID` selects Inbox-dependent HTTP execution but does not
  authorize it.
- `legacy` and `explicit` replace `auto` and reject mixed configuration.
- The old per-Inbox callback path and example send endpoints are removed.
- Error mappings and all-or-nothing intake changed.
- Host migration steps and breaking public imports.

Do not say Wappa implements Instagram credentials, exactly-once delivery,
database-enforced read-only sessions, replica cooldown, or multi-Meta-App
support.

## Release procedure

After every runtime and documentation PRD passes:

1. Confirm version metadata and lock file both say `0.27.0`.
2. Run Ruff, formatting check, mypy, full pytest, and `git diff --check`.
3. Build wheel and source distribution from a clean release commit.
4. Inspect artifact contents and install the wheel in a clean environment.
5. Confirm the installed package reports `0.27.0` and public import smoke tests
   pass.
6. Review the changelog against the decision checklist above.
7. Create the repository-format release commit and signed or annotated
   `v0.27.0` tag according to the existing release workflow.
8. Push the tag only with operator approval. Let the configured GitHub Action
   publish to PyPI.
9. Verify the GitHub Actions job succeeded and PyPI serves `wappa==0.27.0`.
10. Install from PyPI in a clean environment. Do not use the local wheel for
    this final check.

Record tag, workflow run, PyPI project/version, artifact hashes, test count, and
installation result in a final release report under `reports/` while this
series remains active.

## Callback cutover and rollback

The Meta dashboard change affects every Inbox under the App. Use this order:

1. Deploy a Host version that answers `/webhook/inboxes/whatsapp`.
2. Change the callback URL and complete GET verification.
3. Send one real message to every active Inbox and confirm the correct handler,
   cache, credential, and reply sender.

Rollback requires both the previous package version and previous Meta callback
URL. Keep the previous package resolvable until acceptance ends.

## Verification

- Run a link check over changed Markdown files.
- Search current docs, code, templates, and examples for the removed callback,
  `auto` routing, Host-defined credential stores, bare account lookup, plaintext
  credential cache rows, and stale Table Cache keyword usage.
- Allow historical reports and superseded ADRs to mention old contracts only
  when they clearly identify them as history.
- Build every generated example or run its documented smoke test.
- Check the wheel's public imports against `docs/public-contract.md`.
- Verify changelog claims against tests or code, not the plan.

## Open questions

None. Tagging, publication, and callback cutover remain approval-gated external
actions, but their required evidence is fixed.

## Exit criteria

- Every canonical DDD, architecture, ADR, and public-contract document agrees
  with the final code.
- README, environment docs, CLI templates, examples, startup text, health docs,
  and OpenAPI teach the same two modes and header rules.
- The migration guide covers legacy and explicit Hosts without mixing them.
- `CHANGELOG.md` actively records the grilling-session decisions and links to
  their documentation.
- Deferred PostgreSQL and delivery-identity work is named without being claimed
  as shipped.
- Git tag `v0.27.0` triggers the configured GitHub Actions release job.
- PyPI serves the exact Wappa v0.27.0 artifact and a clean install passes smoke
  tests.
- A final release report records verifiable evidence.
