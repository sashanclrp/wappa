---
version: 1.0.0
last_reviewed: 2026-08-30
status: implemented_awaiting_release_approval
author: implementation report
plan: docs/backlog/in_progress/260829-wappa-v0.27.0/plan.md
decided_by: docs/grill-me-sessions/260829_wappa-v0.27.0-multi-inbox-hardening.md
candidate_version: 0.27.0
---

# Release report — Wappa v0.27.0 multi-Inbox hardening

## Scope delivered

All six Wappa PRDs in `../wappa/` are implemented in the working tree on top of commit `bae8470` (v0.26.3). Nothing is committed, tagged, or published; those are the operator-gated external actions listed at the end.

| PRD | Delivered by |
| --- | --- |
| 1 Runtime identity and Table Cache scope | `wappa/domain/inbox/identity.py` (`InboxRef`, `PlatformAccountRef`), `wappa/persistence/scope.py` (`SYSTEM_SCOPE`, `create_system_table_cache`), `context_id` on `RedisTable` / `MemoryTable` / `JSONTable` / `ICacheFactory.create_table_cache` |
| 2 Encrypted Inbox Directory | `wappa/domain/inbox/{credentials,errors,ports,services,settings_resolver,routing}.py`, `wappa/core/security/credential_codec.py`, `wappa/persistence/inbox_directory.py` |
| 3 Authenticated intake and WABA membership | `wappa/core/config/meta_application.py`, `wappa/core/inbound/meta_callback_auth.py`, `wappa/core/inbound/webhook_routing.py`, `wappa/api/controllers/webhook_controller.py`, `wappa/api/routes/webhooks.py` |
| 4 HTTP execution and routing modes | `wappa/api/dependencies/inbox_context.py`, `wappa/api/dependencies/{whatsapp,cache}_dependencies.py`, `wappa/api/middleware/inbox.py`, `wappa/core/factory/inbox_assembly.py`, `WappaBuilder` / `Wappa` / `WappaCorePlugin`, `wappa/api/routes/health.py`, demo routes removed |
| 5 Failure semantics and verification | typed errors in `wappa/domain/inbox/errors.py`, `wappa/core/dispatch/context_builder.py` (one builder for webhook, API, cron, external), `InboundRuntime` rewrite (dead `accept_webhook` removed), `WappaEventHandler.require_database()`, the test groups below |
| 6 Docs, migration, release | `CONTEXT.md`, `ARCHITECTURE.md`, persistence docs, ADR-0010 amended, ADR-0011 added, `docs/public-contract.md`, `docs/migration/v0.27.0-multi-inbox.md`, README, `.env.example`, CLI env template, example env files and startup validation, Railway guide, `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md` |

Replaced first-slice pieces: `IInboxCredentialStore`, `DatabaseInboxCredentialStore` / `wappa_inboxes`, `SettingsInboxCredentialStore`, `select_inbox_credential_store`, `auto` routing, the verify-token HMAC helper, broad `/api/whatsapp/*` middleware, `401` for unknown payload Inboxes, plaintext cache rows, bare-string account lookup.

## Verification on the final candidate

Run on 2026-08-30 against the working tree:

| Gate | Result |
| --- | --- |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 412 files already formatted |
| `uv run mypy wappa` | Success: no issues found in 352 source files |
| `uv run pytest -q` | **920 passed, 1 skipped** (the skip is the JSON-backend sliding-TTL case; Redis-backed directory and Table Cache cases ran against the local Redis) |
| `git diff --check` | clean |
| `uv build` | `dist/wappa-0.27.0-py3-none-any.whl`, `dist/wappa-0.27.0.tar.gz` |
| Wheel inspection | 352 `.py` modules including `wappa/domain/inbox/*`, `wappa/core/security/*`, `wappa/core/dispatch/*`, `wappa/persistence/{scope,inbox_directory}.py`, `wappa/core/config/meta_application.py`, `wappa/core/factory/inbox_assembly.py`, `wappa/core/inbound/meta_callback_auth.py`, `wappa/api/dependencies/inbox_context.py`; `METADATA` reports `Version: 0.27.0` and `Requires-Dist: cryptography>=43.0.0`; README, CHANGELOG, CLI templates, and example `.env.example` files are packaged |
| Clean-venv install of the wheel | `importlib.metadata.version("wappa") == "0.27.0"`, `wappa.__version__ == "0.27.0"`, every supported public import resolves, `create_system_table_cache("memory").context_id == "__system__"` |

Artifact hashes (SHA-256):

```text
dea795b3a418b99c5c8d9d6cbf03ed4528a680956b29ef7e246522b246a15aba  wappa-0.27.0-py3-none-any.whl
d72ffa4888afbf752e03bf95db1fe129eceda4517e25c8c87805c8e729bb655b  wappa-0.27.0.tar.gz
```

Baseline before this series: 576 passed on the first candidate; 889 at the end of the implementation pass, 920 after the gap-closing audit below.

## Gap-closing audit

Five review agents re-read the implementation against the six PRDs after the initial pass. Their findings were applied in full; nothing was deferred.

Code and contract gaps closed:

- Template routes resolved the Inbox Directory **twice** per request — once in `get_inbox_execution_context`, again inside `OutboundRuntime._messenger`. `ResolvedInboxCredentials` now threads through `OutboundRuntime.templates()` → `InboxTemplateTransport` → `_messenger`, and `InboxExecutionContext.template_transport(app)` is the one way an HTTP route reaches Template transport. Two tests pin the reuse and the non-HTTP fallback.
- `X-Wappa-Inbox-ID` was invisible in the OpenAPI schema. It is now a declared `Header` parameter (`InboxIdHeader`), asserted against a real `app.openapi()` document on every Inbox-dependent route.
- `create_context` silently degraded typed `InboxDirectoryError`s into an unclassified `AttributeError` on the cron and external paths; it now re-raises them, and `event_dispatcher` reports `error_type` so a failure category survives to the caller.
- The renamed Table Cache keyword failed with a bare `TypeError`. `resolve_table_context_id` now raises a message naming the rename, the new `context_id` keyword, the fact that no cache migration is needed, and the migration document — across all three backends and their factories.
- A dead second authentication call site (`validate_webhook_signature` on `BaseProcessor` and the WhatsApp Processor) was removed; `request_logging` redacted a header name (`x-whatsapp-hub-signature`) that no longer exists.
- `wappa init` and its `.env` now teach `META_APP_SECRET`, `WP_WEBHOOK_VERIFY_TOKEN`, the one callback URL, and the auth-vs-verify distinction.

Test coverage added: CLI scaffolding contract (7 tests), concurrent-request context isolation, pre-authentication logging (no payload content, no App Secret in logs or responses), media upload and Template sends in the route capability matrix, typed-failure propagation through the shared context factory, and the Table Cache migration-guidance message.

Documentation repaired: seven broken Markdown links (including `CONTRIBUTING.md`, which README linked to but which did not exist), a **wrong license statement** (MIT) shipped in the full example's README, `AuthPlugin.md`'s conflation of `DEFAULT_EXCLUDES` with the public-route-prefix seam, `Owner`/`tenant`/`provider` language surviving in six plugin and architecture documents, stale environment variable names in Docker/Railway deployment files and example READMEs, six examples whose onboarding never mentioned `META_APP_SECRET`, a Redis persistence README describing an entirely different codebase (deleted — it shipped in the wheel), and two zero-byte example READMEs (written). A repo-wide link checker reports no broken relative links across 107 Markdown files.

## Test groups added or rewritten

- `tests/test_inbox_identity.py`, `tests/test_table_cache_context_scope.py` — cross-Platform collisions, namespace encoding, `context_id` rename with byte-identical keys, stale keyword rejection, System Scope builder, backend conformance.
- `tests/test_credential_codec.py`, `tests/test_inbox_credential_records.py` — binding, redaction, masked-envelope rejection, active/previous keys, rotation, lost keys, record union rules, index records, credential service commands.
- `tests/test_inbox_directory.py` — memory/JSON/Redis conformance: cold/warm reads, sliding vs. fixed TTLs, negative caching, outages without negative rows, concurrent misses, version ordering, equal-identical retry repair, deactivation, reactivation versions, absent refresh, partial index repair, account moves, fan-out membership, stale-index repair, repair failure, integrity failures, shared physical tokens, plaintext never stored, ciphertext copies, previous-key rewrite.
- `tests/test_meta_callback_auth.py`, `tests/test_whatsapp_payload_routing.py`, `tests/test_multi_inbox_webhook_context.py`, `tests/test_webhook_auth_contract.py` — exact-byte HMAC, generic 401s, no directory call before authentication, object-root 400s, phone/WABA membership, fan-out, unknown-Inbox 400, outage 503, mixed batch schedules nothing, GET verification isolation, removed routes 404, per-Inbox isolation and ambient-context reset.
- `tests/test_inbox_routing_modes.py`, `tests/test_inbox_execution_context.py` — legacy/explicit startup matrix, forbidden mixed settings, encryption key validation, Meta configuration sources, health redaction, the full route capability matrix (header present/absent/malformed/unknown/unavailable/legacy default), one directory resolution per request, local-only routes independent of directory health, auth before selection, media metadata with the selected token, Template WABA from the record.
- `tests/test_dispatch_context_builder.py`, `tests/test_public_contract_imports.py` — shared builder across paths, optional `db` / `db_read` without fake sessions, eviction subscription, removed modules, supported imports.

## Observability checks

Health and startup logs distinguish the selected routing mode, callback configuration readiness, directory configured versus reachable, directory unavailable versus Inbox absent (typed errors), credential integrity failures without record contents, and background dispatch failure categories. Tests assert tokens, envelopes, App Secrets, and encryption keys never appear in health output, representations, or exception messages.

## Known limits (named, not shipped)

- PostgreSQL plugin hardening (enforced read-only `db_read`, replica cooldown, `ReadFallbackPolicy`, telemetry) is separate backlog work.
- Delivery identity: v0.27 keeps at-least-once delivery and defines no fingerprint.
- Only WhatsApp credential records ship; the union is designed to grow per Platform.
- The JSON backend keeps one file-level expiry per scope, so sliding and fixed TTLs coincide there; it is a single-process development backend.

## Operator-gated actions still pending

1. Add `META_APP_SECRET` to every environment that mounts the callback (the repository `.env` currently has only `WP_WEBHOOK_VERIFY_TOKEN`; a full `Wappa` app will refuse to start without it).
2. Commit the release in the repository format and create the annotated `v0.27.0` tag.
3. Push the tag with operator approval; `.github/workflows/publish.yml` builds and publishes to PyPI via trusted publishing.
4. Verify the GitHub Actions run and that PyPI serves `wappa==0.27.0`; install from PyPI in a clean environment (the local wheel does not count for this final check) and record the result here.
5. Meta callback cutover per `docs/migration/v0.27.0-multi-inbox.md` (two-part rollback: package version and callback URL together).
6. Symphonai adoption (`../symphonai/`) against the published package, then delete this series directory.
