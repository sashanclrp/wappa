---
version: 1.0.0
last_reviewed: 2026-08-29
status: historical_candidate_report
author: implementation report
reviews: docs/backlog/in_progress/260829-wappa-v0.27.0/reports/260829-high-payload-routed-multi-inbox-webhooks.md
decided_by: docs/adr/0010-payload-routed-whatsapp-webhook.md
candidate_version: 0.27.0
superseded_by: docs/backlog/in_progress/260829-wappa-v0.27.0/plan.md
---

# Implementation report — payload-routed multi-Inbox webhooks

## How to use this document

This is the engineering companion to the work item it reviews. It describes what the code actually does, where the seams are, which invariants are load-bearing, and where a reviewer should spend attention. It is written to be read alongside a diff, not instead of one.

Nothing described here is committed. All of it lives in the working tree at candidate version `0.27.0`, 48 files changed, +1355/−317, plus five new paths.

**Verification at time of writing:** `uv run ruff check .` clean · `uv run ruff format --check .` clean, 387 files · `uv run mypy wappa` clean, 336 source files · `uv run pytest -q` 576 passed · `git diff --check` clean.

## 1. The change in one paragraph

Inbox identity moved from the webhook URL into the webhook payload. Previously `/webhook/inboxes/{inbox_id}/whatsapp` made a configuration-controlled URL segment the routing authority, which cannot represent two phone numbers behind one Meta App, because Meta allows one callback URL per App. Now a single callback at `GET + POST /webhook/inboxes/whatsapp` splits each provider batch into one delivery per change, derives each delivery's Inbox from `value.metadata.phone_number_id` (or a flat `value.phone_number_id`), falls back to WABA-scoped fan-out through the credential store when a change carries no phone number, and validates every derived Inbox before any handler work is scheduled. Alongside it, credential-store selection became explicit and all-or-nothing, and identity resolution became Inbox-scoped.

## 2. Routing authority, before and after

```
BEFORE
  Meta ──POST /webhook/inboxes/{inbox_id}/whatsapp──> InboxMiddleware
                     │                                     │
            (config-controlled)                   binds inbox_id from URL
                                                           │
                                              InboundRuntime validates that
                                              payload.metadata.phone_number_id
                                              matches the URL, else rejects

AFTER
  Meta ──POST /webhook/inboxes/whatsapp──> InboxMiddleware  (binds nothing for /webhook/*)
                                                  │
                                     route_whatsapp_payload(payload, store)
                                                  │
                              ┌───────────────────┴───────────────────┐
                       phone-scoped change                  WABA-only change
                    metadata.phone_number_id           store.get_inbox_ids_for_
                    or flat phone_number_id            platform_account(entry[].id)
                              │                                       │
                              └──────────► one delivery per (change, inbox) ◄──┘
                                                  │
                                InboundRuntime.accept_webhook_batch
                                  builds ALL contexts, then schedules
```

The critical inversion: the URL is no longer trusted, and the signed provider payload is. `entry[].id` is the WABA — Provider Account identity — and is never used as an Inbox.

## 3. New module: `wappa/core/inbound/webhook_routing.py`

The only genuinely new logic. Pure, dependency-light, and the natural first read for a reviewer.

**Public surface:** `route_whatsapp_payload(payload, credential_store) -> tuple[RoutedWebhookDelivery, ...]`, plus `RoutedWebhookDelivery(inbox_id, payload)` and two errors, `ProviderWebhookRoutingError` and its subclass `PlatformAccountNotRegisteredError`.

**Algorithm, in order:**

1. Reject the payload unless `object == "whatsapp_business_account"`.
2. Require a non-empty `entry` list. For each entry, require a non-empty string `entry.id` (the WABA) and a non-empty `changes` list.
3. For each change, require `value` to be an object. If `value.waba_id` is present, it must equal `entry.id`, else reject — this catches a payload whose two identity fields disagree.
4. Resolve the change's Inbox candidates (below).
5. Rebuild an isolated single-change payload and emit one delivery per candidate:

```python
unit_entry = {**entry, "changes": [change]}
unit_payload = {**payload, "entry": [unit_entry]}
```

Note this preserves every sibling key on both the payload and the entry, so downstream provider translation sees a structurally valid Meta payload rather than a fragment.

**Candidate resolution** (`_resolve_change_inbox_ids`):

- Read `value.metadata.phone_number_id` and flat `value.phone_number_id`. If both are present and differ, reject — Wappa does not pick a winner between two identity claims.
- If either is present, that single value is the Inbox.
- Otherwise ask the store: `get_inbox_ids_for_platform_account(entry.id)`, then `tuple(sorted(set(resolved)))`.
- An empty result raises `PlatformAccountNotRegisteredError`. Wappa never invents a scope and never selects a first or default Inbox.

**Why `sorted(set(...))` is load-bearing.** De-duplication prevents Wappa itself from adding a duplicate-delivery multiplier on top of Meta's retries. Sorting makes fan-out replay deterministic, because a host store backed by SQL can return rows in an order that shifts with plan or index changes. `DatabaseInboxCredentialStore` does specify `ORDER BY inbox_id`, but the routing layer normalises anyway rather than trusting every host implementation. `tests/test_whatsapp_payload_routing.py` encodes this adversarially: its store returns `("phone-2", "phone-1", "phone-2")` and the assertion is `["phone-1", "phone-2"]`, so the test fails if either `set()` or `sorted()` is removed. The out-of-order first element is deliberate — a pre-sorted fixture could not distinguish sorting from input-order preservation.

## 4. Error taxonomy and HTTP mapping

`WebhookController.process_webhook` translates routing and runtime errors into status codes. The mapping is the contract hosts will observe, so it deserves direct review:

| Raised | Status | Meaning |
| --- | --- | --- |
| `PlatformAccountNotRegisteredError` | 401 | WABA has no registered active Inbox. Fails closed. |
| `ProviderWebhookRoutingError` | 400 | Malformed payload, conflicting identities, WABA mismatch. |
| any other exception during routing | 503 | Credential store outage while enumerating Inboxes. |
| `InvalidInboxError` | 401 | A derived Inbox is unknown or inactive. |
| `InboxCredentialStoreUnavailableError` | 503 | Store raised during `validate_inbox`. |
| `PayloadInboxMismatchError` | 400 | Provider translation produced an Inbox other than the routed one. |
| `ProcessorFailureError` | 400 | Provider translation failed. |
| `UnsupportedPlatformError` | 400 | Platform not implemented. |

The distinction that matters operationally: **an outage is 503, an unknown Inbox is 401.** Collapsing those would make a Postgres blip look like a misconfigured Meta App during an incident. `build_dispatch_context` enforces this by wrapping only the `validate_inbox` call in its own `try`, converting any raised exception into `InboxCredentialStoreUnavailableError` rather than letting it fall through to the generic 500 handler.

## 5. Batch semantics — the no-partial-dispatch guarantee

`InboundRuntime.accept_webhook_batch` (`wappa/core/inbound/runtime.py:127`) is deliberately two loops, not one:

```python
dispatch_contexts = [
    await self.build_dispatch_context(...)
    for inbox_id, payload in deliveries
]
for dispatch_context in dispatch_contexts:
    dependencies.background_work_tracker.track(self.dispatch(dispatch_context), ...)
```

Every context — which includes Inbox validation, provider translation, user resolution, Messenger construction, and cache-factory construction — is built for the whole batch before the first task is scheduled. A failure on change 7 of 8 therefore rejects the entire HTTP request with nothing dispatched, rather than leaving six handlers running against a request Meta will retry in full. Pinned by `tests/test_multi_inbox_webhook_context.py::test_invalid_later_change_schedules_none_of_the_batch`.

Reviewers should note this is a deliberate latency-for-correctness trade: a large batch does all of its I/O-bound validation serially before any work starts.

## 6. Context propagation — verified, non-obvious

This is the subtlest part of the change and the one most likely to raise a reviewer's eyebrow.

`build_dispatch_context` calls `set_request_context(inbox_id=..., user_id=...)` at `runtime.py:185`, once per delivery, inside the build loop. Because all builds share one async context, after the loop the contextvar holds the **last** delivery's values, not each delivery's. Two consequences were traced:

1. **Data scoping is unaffected.** Nothing that determines where data lands reads the contextvar. `_create_dispatch_handler` receives `inbox_id` and `user_id` as explicit parameters and passes them explicitly into `MessengerFactory.create_messenger(...)` and `factory_class(inbox_id=..., user_id=...)`. Cache keys, Messenger credentials, and identity resolution all come from parameters, not ambient context.
2. **Task scheduling is safe.** `track()` creates tasks after the build loop, so each task inherits a context copy holding the last delivery's values — but `dispatch()` (`runtime.py:224`) re-binds `set_request_context(inbox_id=..., user_id=...)` from its own `DispatchContext` as its first statement, inside the task's own context copy. Handler work is therefore correctly scoped, and the rebinding does not leak back to the caller.

The residual effect is **log attribution during the build phase only**: a log line emitted between builds is tagged with whichever delivery was built most recently. Worth a reviewer's opinion on whether to bind/reset per build iteration for cleaner correlation; it is cosmetic today.

On the HTTP side, `InboxMiddleware.dispatch` now brackets the whole request with `bind_inbox_context(None)` / `reset_inbox_context(token)` in a `finally`, so a header-supplied Inbox cannot survive into the next request on the same worker. Covered by `tests/test_db_only_inbox_boot.py::test_inbox_context_does_not_leak_between_requests`.

## 7. The outbound HTTP seam — `X-Wappa-Inbox-ID`

Webhook intake derives its Inbox from content. Wappa's own non-webhook WhatsApp API routes have no payload to derive from, so the caller names the Inbox in a header. `InboxMiddleware` (`wappa/api/middleware/inbox.py`) owns this and no longer reads `WP_PHONE_ID` directly.

Resolution order for a non-webhook, non-public route:

1. `X-Wappa-Inbox-ID` if present — format-checked, then existence-checked against `IInboxCredentialStore.validate_inbox`.
2. Otherwise `credential_store.default_inbox_id`, which only `SettingsInboxCredentialStore` provides, and which explicit mode suppresses entirely (`app.state.inbox_routing != "explicit"`).
3. Otherwise, for `/api/whatsapp/*`, reject 400.

| Condition | Status |
| --- | --- |
| Header fails format check (alphanumeric plus `-`/`_`, 3–50 chars) | 400 |
| Header names an Inbox the store does not know | 404 |
| Store raises while validating the header | 503 |
| `/api/whatsapp/*`, no header, no store default | 400 |

The format check runs **before** the store call, so a malformed value cannot be masked as a 503 by a degraded store. `tests/test_db_only_inbox_boot.py::test_malformed_explicit_http_inbox_is_rejected_before_the_store` asserts this using a store that always raises.

Status-code rationale for review: 404 says the named Inbox is not one this deployment owns, which is a different failure from omitting the header (400) and from the store being down (503). Webhook-derived Inboxes keep 401 to match the pre-existing documented webhook contract.

**Performance consequence.** `validate_inbox` is now on the hot path for both every payload-derived delivery and every Inbox-scoped API call. `DatabaseInboxCredentialStore` serves it from a Redis read-through cache with Postgres as authority. A host store that does an uncached query per call will turn one batched or fanned-out webhook into a burst of database round-trips. This is documented as a store implementer obligation in `docs/public-contract.md`.

Note that `build_dispatch_context` validates independently of the middleware, because it is reachable outside the HTTP path.

## 8. Credential store contract and selection

**Interface additions** (`wappa/domain/interfaces/inbox_credential_store.py`):

- `get_inbox_ids_for_platform_account(platform_account_id) -> tuple[str, ...]` — abstract, required of every host store. Breaking.
- `default_inbox_id -> str | None` — concrete, defaults to `None`. Only `SettingsInboxCredentialStore` overrides it.

**`DatabaseInboxCredentialStore`** reads a host-owned `wappa_inboxes` table: `inbox_id` (PK), `platform`, `access_token`, `platform_account_id`, `is_active`. Both the single lookup and the account enumeration filter `is_active = TRUE`; the enumeration adds `ORDER BY inbox_id`. `is_active` is also honoured on the Redis cache read path, so deactivating an Inbox is not defeated by a warm cache.

**Selection** (`select_inbox_credential_store`, `wappa/domain/services/inbox_credentials_service.py`) is where reviewers should look hardest, because it decides which credentials a deployment actually uses:

- Identity variables are `WP_PHONE_ID` and `WP_BID` only. `WP_ACCESS_TOKEN` is classified as a **provider secret, not Inbox identity**, so a host may keep a shared token in the environment while resolving Inboxes from its database.
- `explicit` mode requires and always selects the injected store, even with a complete legacy bundle present.
- `auto` mode with a complete bundle selects `SettingsInboxCredentialStore`, and emits a `UserWarning` naming the store that won if an injected store was also supplied. Precedence is no longer silent.
- Partial identity (one of `WP_PHONE_ID`/`WP_BID`) raises `OSError`.
- `WP_ACCESS_TOKEN` alone with no injected store raises `OSError` explaining that a token does not identify an Inbox.

Mode is plumbed as a plain validated string, not an enum: `Wappa(inbox_routing=...)` (`wappa_app.py:68`) → `WappaBuilder.with_inbox_routing()` (`wappa_builder.py:331`) → selection and `app.state.inbox_routing` (`wappa_builder.py:427,431`). A reviewer may reasonably ask for a `Literal["auto","explicit"]` here.

## 9. Startup validation moved out of import

`Settings.__init__` no longer validates WhatsApp credentials. `Settings.validate_whatsapp_configuration(require_settings_inbox_credentials=...)` is called from `WappaCorePlugin` at startup, once the selected store is known. It always requires `WP_WEBHOOK_VERIFY_TOKEN`, and requires the three `WP_*` values only when the settings store was selected. This is what allows a database-backed deployment to boot with no Inbox credentials in its environment at all.

## 10. Cache-key impact — none

A predictable review question: does any of this change Redis keys? No.

Key construction never consulted settings. `KeyFactory` takes `inbox` as a plain argument and produces `{inbox}:user:{user_id}`, `{inbox}:state:{name}:{user_id}`, `{inbox}:df:{table}:pkid:{pk}`, `{inbox}:EXPTRIGGER:{action}:{ident}`, `{inbox}:aistate:{agent}:{user_id}`, and channel `wappa:notify:{inbox}:{user}:{event}`. That argument comes from `ICacheFactory.__init__(inbox_id, user_id)`, which the Inbound Runtime constructs with the routed `inbox_id`.

Keys are therefore byte-identical to the previous release **provided the `inbox_id` string is unchanged**, and it is: for WhatsApp, `inbox_id` is the Meta `phone_number_id` both before and after. This is enforced, not merely conventional — `_validate_payload_inbox` rejects a delivery whose translated payload Inbox differs from the routed one, so a host cannot register Inboxes under its own UUIDs without every webhook failing.

**Migration implication for host stores:** `wappa_inboxes.inbox_id` must hold the `phone_number_id`.

## 11. Test map

| Requirement | Test |
| --- | --- |
| metadata / flat phone routing, conflict rejection | `test_whatsapp_payload_routing.py::test_metadata_phone_number_id_is_the_inbox`, `::test_flat_phone_number_id_is_the_inbox`, `::test_metadata_and_flat_phone_number_ids_cannot_conflict` |
| WABA fan-out, de-dup, sort | `::test_waba_scoped_change_fans_out_to_every_registered_inbox` |
| WABA never used as Inbox; zero-Inbox fails closed | `::test_entry_id_is_never_used_as_an_inbox_fallback` |
| WABA mismatch | `::test_flat_waba_id_must_match_entry_id` |
| batch split order | `::test_batched_changes_split_in_entry_and_change_order` |
| isolated per-Inbox contexts | `test_multi_inbox_webhook_context.py::test_webhooks_from_multiple_inboxes_get_isolated_handler_contexts`, `::test_waba_only_event_fans_out_with_isolated_inbox_contexts` |
| no partial batch dispatch | `::test_invalid_later_change_schedules_none_of_the_batch` |
| store outage → 503 | `::test_credential_store_outage_during_payload_validation_returns_503` |
| payload/route mismatch | `::test_inbound_runtime_rejects_payload_inbox_mismatch` |
| explicit mode beats legacy bundle | `test_inbox_credential_store.py::test_explicit_routing_forces_custom_store_over_complete_settings_bundle`, `::test_explicit_routing_never_exposes_a_custom_store_default` |
| auto-mode ambiguity warning | `::test_complete_settings_bundle_selects_legacy_store_over_custom_store` |
| Provider Account enumeration | `::test_database_store_lists_distinct_inboxes_for_platform_account` |
| rotation invalidates both cache layers | `::test_messenger_factory_invalidation_clears_both_cache_layers`, `::test_outbound_runtime_invalidation_clears_both_cache_layers` |
| header 400 / 404 / 503, context isolation | `test_db_only_inbox_boot.py::test_malformed_explicit_http_inbox_is_rejected_before_the_store`, `::test_explicit_http_inbox_is_validated_against_the_credential_store`, `::test_unavailable_credential_store_is_not_reported_as_unknown_inbox`, `::test_inbox_context_does_not_leak_between_requests` |
| DB-only boot without WP_* identity | `::test_core_boots_custom_store_without_single_inbox_environment`, `::test_core_boots_custom_store_with_shared_environment_access_token` |
| live route set pinned, old route 404 | `test_webhook_auth_contract.py::test_router_exposes_canonical_processing_and_verify_only_routes`, `::test_removed_per_inbox_webhook_route_returns_not_found` |
| URL factory safe without WP_PHONE_ID | `::test_webhook_url_factory_is_safe_without_environment_inbox` |

## 12. Review focus areas

Ranked by how much a second opinion would help.

1. **`InboundRuntime.accept_webhook` is now dead code.** `runtime.py:105`. The single-delivery entry point has no caller anywhere in the repo; the controller uses `accept_webhook_batch` exclusively. It is not exported in the public contract. Recommend deleting it, or documenting it as a supported programmatic entry point. Leaving an unused second dispatch path invites divergence.
2. **Batch-build context attribution** (section 6). Correct for data, imprecise for logs. Decide whether to bind/reset per iteration.
3. **`{platform}` path parameter versus a `whatsapp` literal.** The work item asks for one canonical path; the route is declared generic and rejects non-WhatsApp platforms with 400 in the controller rather than 404 at the router. Recorded as a decision in ADR-0010 and constrained by a route-set test, but it is a deviation and should be confirmed, not inherited.
4. **`inbox_routing` is an unvalidated-at-type-level string.** Runtime membership check only. A `Literal` would move the error to type-check time.
5. **Serial validation cost for large batches** (section 5). Confirm the trade is acceptable at expected Meta batch sizes.
6. **Fan-out amplification.** One account-scoped change becomes `N` deliveries for `N` active Inboxes under a WABA, each performing an Inbox validation and Messenger construction. Watch delivery counts per request after cutover.

## 13. Known gaps carried into this release

Documented in the work item; repeated here so reviewers do not rediscover them as defects.

- **Host idempotency is unenforced.** Wappa delivers at least once and supplies no delivery fingerprint. Three multipliers — Meta retries, batch splitting, WABA fan-out — can present one provider event repeatedly. Account-scoped handlers mutating shared state must be idempotent. This is the largest residual risk in the change and it lives outside Wappa.
- **`WebhookPlugin` diverges.** External non-Meta webhook sources still take `inbox_id` from `/webhook/{source}/{inbox_id}` and bind no Inbox context; they thread the id explicitly into their runtime. Pre-existing and unchanged, but it now sits beside a WhatsApp path with the opposite philosophy. Any code reached from it that calls `require_inbox_context()` will raise.
- **`parse_inbox_from_expired_key` falls back to the literal `"wappa"`** when an expired Redis key has no separator. Harmless single-Inbox; in multi-Inbox it runs an expiry handler against a fabricated namespace.

## 14. Cutover and rollback

The Meta callback URL is the only step not reversible inside the repository. It is dashboard configuration, it applies to every Inbox under the App simultaneously, and events arriving between deploy and reconfiguration hit the removed route and 404.

Order: deploy → change the Meta callback URL and re-run verification → confirm a real message per Inbox before declaring done.

**Rollback is a two-system operation.** Reverting the Wappa version while leaving the new callback URL configured — or the reverse — produces total delivery failure, not degraded service. Both must revert together. Confirm the previous Wappa version is resolvable before starting, and schedule the cutover when someone can watch delivery.

## 15. File inventory

**New**

- `wappa/core/inbound/webhook_routing.py` — payload routing, batch splitting, WABA fan-out.
- `tests/test_whatsapp_payload_routing.py` — routing unit tests.
- `tests/test_db_only_inbox_boot.py` — DB-only boot, header contract, context isolation, health output.
- `docs/adr/0010-payload-routed-whatsapp-webhook.md` — the decision.

**Materially changed**

- `wappa/api/routes/webhooks.py` — route shape.
- `wappa/api/controllers/webhook_controller.py` — routing call and error mapping.
- `wappa/core/inbound/runtime.py` — batch acceptance, store-outage error, validation order.
- `wappa/api/middleware/inbox.py` — no webhook URL parsing; header seam with existence validation; per-request bind/reset.
- `wappa/domain/interfaces/inbox_credential_store.py` — account enumeration, `default_inbox_id`.
- `wappa/domain/services/inbox_credentials_service.py` — selection rules, ambiguity warning.
- `wappa/domain/services/database_inbox_credential_store.py` — account query, active filtering.
- `wappa/domain/interfaces/identity_resolver.py` — Inbox-scoped `resolve`.
- `wappa/core/factory/wappa_builder.py`, `wappa/core/wappa_app.py` — routing mode plumbing.
- `wappa/core/config/settings.py` — validation moved to startup, mode-aware.
- `wappa/core/plugins/wappa_core_plugin.py` — startup validation and banner.
- `wappa/core/events/webhook_factory.py` — canonical URL, no `settings.inbox_id`.
- `wappa/api/routes/health.py` — store-derived output.
- `wappa/domain/factories/messenger_factory.py`, `wappa/messaging/template_transport.py` — rotation invalidation across both cache layers.

**Docs**

`CONTEXT.md`, `ARCHITECTURE.md`, `docs/public-contract.md`, `CHANGELOG.md`, `.env.example`, `docs/adr/0001` (superseding banner), `wappa/webhooks/{ARCHITECTURE,CONTEXT}.md`, `wappa/core/plugins/README/AuthPlugin.md`, and the Railway example.

## 16. Outstanding before release

- Confirm the previous Wappa version is resolvable for rollback.
- Manual `wappa_miia` acceptance: both Owners receiving and replying on their own numbers, each conversation resolving to its own Chat with no cross-Owner leakage, outbound leaving from the correct number, clean logs. Automated tests do not substitute — Miia is the only deployment that can demonstrate the cross-Inbox isolation this work exists for.
- Operator review and naming of the approved release. Nothing is tagged or published by this work item.
