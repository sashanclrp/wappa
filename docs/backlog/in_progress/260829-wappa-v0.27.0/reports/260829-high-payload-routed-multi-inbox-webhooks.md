---
version: 0.2.0
last_reviewed: 2026-08-29
status: superseded_by_feature_series
author: sasha
urgency: high
owner: Wappa Inbound Runtime and credential contracts
blocked_by: operator acceptance, wappa_miia manual acceptance, and release approval
decided_by: docs/adr/0010-payload-routed-whatsapp-webhook.md
superseded_by: docs/backlog/in_progress/260829-wappa-v0.27.0/plan.md
---

# Payload-routed multi-Inbox webhooks and explicit host credential mode

## Outcome

Wappa accepts WhatsApp verification and delivery through one callback URL, `/webhook/inboxes/whatsapp`. A POST derives each Inbox from the Meta payload, validates it through the configured `IInboxCredentialStore`, and builds a separate Dispatch Context for each routed change. The URL never supplies Inbox identity.

Wappa still supports legacy single-Inbox applications. Symphonai does not use that mode after this work. Symphonai always injects its credential store and forces explicit routing, even if old `WP_PHONE_ID` or `WP_BID` values remain in a deployment by mistake.

## Why this work exists

Meta configures one callback URL per App. A URL shaped as `/webhook/inboxes/{inbox_id}/whatsapp` cannot represent two WhatsApp phone numbers behind the same Meta App without asking Meta to call different URLs. It also places trusted runtime identity in a path controlled by configuration rather than in the signed provider payload that names the phone number that received the event.

Symphonai is moving to a hard Owner boundary. Its durable chain is:

```text
Meta payload phone_number_id
  -> Wappa Inbox
  -> Symphonai Owner Channel
  -> Owner
  -> Chat
  -> Conversation and Message
```

Miia exposes the defect because it has two Owners. The same WhatsApp user may contact both phone numbers and must produce two isolated Chats. Other Symphonai Thin Consumers currently have one Owner and one Inbox, but they should run the same explicit contract. Adding a second Owner Channel later must require data and configuration, not a different Wappa boot mode.

Wappa must not learn Symphonai's Owner or Owner Channel language. Wappa owns provider Inbox extraction, credential lookup, Messenger construction, cache scope, and handler dispatch. Symphonai maps the resulting `inbox_id` to its business boundary.

## Fixed decisions

### One WhatsApp webhook URL

The only live WhatsApp callback routes are:

```text
GET  /webhook/inboxes/whatsapp
POST /webhook/inboxes/whatsapp
```

GET handles Meta's `hub.challenge` verification with `WP_WEBHOOK_VERIFY_TOKEN`. Verification has no message payload and needs no Inbox context.

POST derives Inbox scope from content. For phone-scoped changes, `value.metadata.phone_number_id` is authoritative. A flat `value.phone_number_id` may supply the same identity for provider event shapes that do not carry `metadata`.

`entry[].id` is a WhatsApp Business Account ID. It is Provider Account identity, not Inbox identity. Wappa never passes it as `inbox_id`.

The route is declared with a `{platform}` path parameter rather than a hardcoded `whatsapp` literal, so one adapter can serve future providers. WhatsApp is the only platform the controller accepts today; every other `PlatformType` value is rejected `400` inside the controller rather than `404` by the router. This is a deliberate deviation from a literal single-path reading of this document. It must stay covered by a test that asserts the router exposes exactly the canonical processing, verification, and status routes, so the generic parameter cannot quietly grow a second live callback shape.

### Clean break for the old route

`/webhook/inboxes/{inbox_id}/whatsapp` is removed. Wappa will not keep an alias, redirect, feature flag, or deprecated handler. GET and POST requests to that shape return 404.

Every application upgrading to this release must change its Meta callback configuration, deployment probes, docs, tests, and any generated URL display. Carrying the old route would keep two routing authorities alive and defeat the purpose of this change.

### WABA-only changes fan out deliberately

Some account and custom-field changes contain a WABA but no phone number ID. The credential store contract therefore exposes a deterministic lookup from `platform_account_id` to every active Inbox registered under that account.

Wappa splits the provider batch into one-change payloads. A phone-scoped change produces one delivery. A WABA-only change produces one delivery per distinct active Inbox returned by the store, sorted for repeatable behavior. No match fails closed. Several matches produce fan-out; Wappa never chooses the first one.

The Inbound Runtime builds every Dispatch Context before it schedules any delivery from the HTTP request. If one change has invalid routing, an inactive Inbox, a payload mismatch, or a processor error, Wappa rejects the request without scheduling a partial batch.

### Wappa has two credential modes

Standalone Wappa keeps an automatic compatibility mode:

- A complete `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, and `WP_BID` bundle selects `SettingsInboxCredentialStore`.
- With no environment Inbox identity, an injected `IInboxCredentialStore` supplies explicit routing. `WP_ACCESS_TOKEN` may remain present as a provider secret.
- Setting only one of `WP_PHONE_ID` or `WP_BID` fails configuration.
- With no complete legacy bundle and no injected store, startup fails.

If automatic mode receives both a complete legacy bundle and an injected store, Wappa warns which store won. Silent precedence is unacceptable because the application may appear database-backed while still routing through environment settings.

Hosts can force explicit mode through Wappa's public constructor or builder contract. Explicit mode requires an injected store, ignores the legacy Inbox bundle for routing, exposes no default Inbox, and requires explicit Inbox scope for outbound HTTP operations.

### Symphonai always chooses explicit mode

After Symphonai adopts this Wappa release, it always forces explicit mode. `WP_PHONE_ID` and `WP_BID` leave every Thin Consumer environment. `WP_ACCESS_TOKEN` and `WP_WEBHOOK_VERIFY_TOKEN` remain for now.

`WP_ACCESS_TOKEN` is a provider secret. Symphonai may use it after its database store has resolved and validated an active Owner Channel, but the token cannot select an Inbox. Per-Owner encrypted credentials may replace the shared token without changing Wappa's routing contract.

Single-Owner and single-Inbox Symphonai deployments still register one Owner Channel in PostgreSQL. Redis may cache that long-lived mapping, but PostgreSQL remains the authority. An unknown or inactive Inbox fails closed.

## Public contract changes

### `IInboxCredentialStore`

The store continues to resolve credentials and validate one Inbox. It also resolves a Provider Account to all active Inboxes:

```python
async def get_credentials(self, inbox_id: str) -> InboxCredentials: ...

async def validate_inbox(self, inbox_id: str) -> bool: ...

async def get_inbox_ids_for_platform_account(
    self,
    platform_account_id: str,
) -> tuple[str, ...]: ...
```

Implementations return a duplicate-free, deterministic tuple. The settings adapter returns its single default Inbox only when `WP_BID` matches. Database adapters query their registered Inbox records.

### Wappa application construction

The application and builder accept an Inbox routing mode. `auto` preserves standalone selection rules. `explicit` requires and selects the injected credential store regardless of a complete environment bundle.

The selected store lives on `app.state.inbox_credential_store`. Health routes and startup output read that same object. They report:

- `configured`, meaning a store exists.
- `credential_store`, the selected class name.
- `default_inbox_id`, which is null in explicit mode.
- `inbox_routing`, either `default` or `explicit`.

### Outbound Inbox scope for Wappa's own HTTP routes

Webhook intake derives its Inbox from payload content. Wappa's non-webhook WhatsApp API routes cannot, because there is no provider payload, so the caller names the Inbox in the `X-Wappa-Inbox-ID` request header.

`InboxMiddleware` owns this seam. It never reads `WP_PHONE_ID` directly. A header value is format-checked, then validated for existence through `IInboxCredentialStore.validate_inbox` before the request reaches a route. Only `SettingsInboxCredentialStore` supplies a default Inbox when the header is absent, and explicit mode suppresses even that. The middleware binds and resets Inbox context per request so a value cannot leak between requests sharing a worker.

`validate_inbox` therefore sits on the hot path for every Inbox-scoped API call and every payload-derived delivery. Store implementations must make it cheap and cached, with the durable store as authority. A store that raises is a dependency outage, not an unknown Inbox, and must be reported as such.

### `IIdentityResolver`

Identity resolution requires Inbox scope:

```python
async def resolve(self, recipient: str, *, inbox_id: str) -> str: ...
```

The same delivery address may identify different users in different Inboxes. Host resolvers that implement the old signature must update before installing this release.

### Webhook URL factory

`generate_whatsapp_webhook_url()` returns the canonical `/webhook/inboxes/whatsapp` URL and never reads `settings.inbox_id`. It must work when `WP_PHONE_ID` is absent.

Generic URL generation, status output, startup logs, examples, and public docs use the same singular callback path. No live helper generates the removed route.

## HTTP behavior

| Condition | Result |
| --- | --- |
| Valid GET challenge and verify token | `200` with the challenge body. |
| Invalid or missing verify token | `403`. |
| Valid phone-scoped POST | `200` with `{"status": "accepted"}` after the Inbox validates. |
| Valid WABA-only POST with registered Inboxes | One accepted delivery per distinct active Inbox. |
| Unknown or inactive derived Inbox | `401`; nothing from the batch is scheduled. |
| WABA with no registered Inbox | `401`; Wappa does not invent a scope. |
| Malformed payload, mixed identity, or WABA mismatch | `400`. |
| Credential store outage during routing | `503`. |
| Old per-Inbox callback route | `404`. |
| `X-Wappa-Inbox-ID` naming an Inbox the store does not know | `404`. |
| `X-Wappa-Inbox-ID` failing the Inbox ID format check | `400`. |
| `/api/whatsapp/*` with no header and no store default | `400`. |
| Credential store outage while validating a header Inbox | `503`. |

The implementation must not include access tokens, webhook secrets, message content, or raw credentials in these errors or logs.

## Delivery semantics

Wappa delivers provider events **at least once**. It does not deduplicate, and it does not promise ordering across deliveries derived from one HTTP request.

Three distinct multipliers can present the same underlying provider event to a handler more than once:

1. Meta retries an unacknowledged or failed callback.
2. Batch splitting turns one HTTP request into one delivery per entry/change pair.
3. WABA fan-out turns one account-scoped change into one delivery per active Inbox under that Platform Account.

The third is new in this release and is the one hosts have never had to absorb before. A WABA carrying `N` active Inboxes multiplies every account-level change by `N`. Handlers that mutate shared, Inbox-independent state on account events — a WABA-level counter, a shared billing record, an outbound notification to an operator — will now do that work `N` times per change.

Wappa's obligations: each fan-out delivery carries exactly one change, is scoped to exactly one validated Inbox, and is emitted in a deterministic Inbox order so repeated runs of the same payload behave identically.

Host obligations: treat account-scoped handlers as idempotent, key any side effect on a provider-supplied identifier rather than on arrival, and do not assume a handler invocation corresponds one-to-one with a provider event. Wappa documents this in the public contract; it cannot enforce it.

If a future release needs stronger semantics, the mechanism is a delivery fingerprint derived from the provider change, not per-Inbox suppression, because suppression would silently drop legitimate per-Inbox work. That is out of scope here.

## Effect on applications that use Wappa

### Legacy standalone applications

Their settings-backed outbound and default-Inbox behavior remains available under `auto`. They must still replace the Meta callback URL with `/webhook/inboxes/whatsapp`. Wappa reads `phone_number_id` from the POST payload and validates that it matches the settings store.

An application that never mounts or receives provider webhooks is not affected by the URL break. It is affected only if it implements `IIdentityResolver` or `IInboxCredentialStore`, because those interfaces change.

### Applications with a custom credential store

These applications gain one callback URL for any number of registered Inboxes. They must implement Provider Account lookup and choose explicit mode when environment leftovers must not override the store.

WABA-only fan-out may call an account-event handler once per registered Inbox. Handlers must treat provider webhook retries and fan-out as repeatable input. Wappa does not promise exactly-once delivery.

### Symphonai and its Thin Consumers

Symphonai gains the Wappa contract required for its Owner Membership refactor. It will resolve inbound `phone_number_id` through `admin.owner_channels`, use the Owner Channel to scope Chat identity, and keep outbound commands tied to an explicit Owner Channel.

Every Thin Consumer eventually removes `WP_PHONE_ID` and `WP_BID`, even when it has one Owner today. Miia is the first proof because it has two Owners. The current Symphonai execution will migrate and validate Miia only; LifePro, Incomer, and Booking keep separate consumer cutover work.

Symphonai stays pinned to its current released Wappa version while this work is reviewed. A local editable install may support development tests, but it is not release evidence. The user will name the approved Wappa release after the implementation and soak checks pass; only then may Symphonai update its package pin and run final `wappa_miia` acceptance against that release.

## Cutover and rollback

The Meta callback URL change is the only step in this work that is not reversible from inside the repository. It is configuration in the Meta App dashboard, it applies to every Inbox under that App at once, and provider events that arrive between the deploy and the dashboard change hit the removed route and `404`.

Cutover order:

1. Deploy the Wappa release. The new canonical route answers; the old route `404`s.
2. Change the Meta callback URL and re-run verification. Meta issues a `GET` challenge against the new URL.
3. Confirm delivery on a real message per Inbox before declaring the cutover done.

Rollback means pinning the host application back to the previous Wappa version **and** restoring the per-Inbox callback URL in Meta. Neither half is sufficient alone. Rolling back the package while leaving the new URL configured, or the reverse, produces total delivery failure rather than degraded service.

Because rollback is a two-system operation, schedule the cutover when someone can watch delivery, and keep the previous Wappa version resolvable for the duration.

## Scope

- Replace the route, middleware, controller, Inbound Runtime, and URL factory contracts with payload-derived Inbox routing.
- Split batched WhatsApp changes by Inbox and support deliberate WABA fan-out.
- Add Provider Account lookup to built-in credential stores and the public interface.
- Add forced explicit credential mode plus an ambiguity warning in automatic mode.
- Make health output and startup logs describe the selected store and routing behavior.
- Remove every live reference, example, test, and generated instruction for the old callback route.
- Ship the Inbox-aware identity resolver contract and migration guidance.
- Update Wappa's candidate version, lock file, changelog, DDD docs, architecture docs, and public contract for the breaking release. A version change does not authorize a tag or publication.

## Out of scope

- Owner, Owner Membership, Owner Channel, Chat, or CRM authorization concepts inside Wappa.
- Symphonai database migrations, Redis Owner Channel cache implementation, frontend Owner selection, or Miia data backfill.
- Removing `WP_ACCESS_TOKEN` or `WP_WEBHOOK_VERIFY_TOKEN`.
- Provider-specific webhook secret storage per Inbox.
- Publishing a Wappa release, tagging Git, pushing commits, or updating the Symphonai dependency pin without direct user approval.
- Exactly-once provider event processing.

## Migration plan for Wappa hosts

1. Implement the new `IIdentityResolver.resolve(..., inbox_id=...)` signature when the host supplies a resolver.
2. Implement `get_inbox_ids_for_platform_account()` when the host supplies a credential store. Confirm that WABA IDs and Inbox IDs remain separate in storage.
3. Select explicit Inbox routing for database-backed hosts. Leave `auto` only for standalone settings-backed deployments that intend to keep a default Inbox.
4. Change the Meta callback and verification URL to `/webhook/inboxes/whatsapp`. Remove path-Inbox probes and configuration.
5. Test one phone-scoped message, one status, one WABA-only event, an unknown phone number ID, and a credential-store outage.
6. Update custom health checks and operator docs. Treat the old route returning 404 as expected.
7. Install the approved released package. Editable source and an unreleased Git checkout do not close the migration.

## Verification

Wappa tests must cover:

- GET verification and POST delivery on the one canonical route.
- 404 for GET and POST on the removed per-Inbox route.
- Payload extraction from metadata and flat phone-number fields.
- Rejection when metadata and flat identities conflict.
- A batch containing changes for two phone-number Inboxes, with isolated handler, cache, Messenger, and identity-resolver context.
- WABA-only fan-out to zero, one, and several registered Inboxes, including duplicate store results.
- Full-batch validation before any dispatch task is scheduled.
- Explicit mode winning over a complete environment bundle.
- Automatic-mode warning when both configuration sources exist.
- Safe URL factory behavior without `WP_PHONE_ID`.
- Health and startup output for default and explicit modes.
- Credential and Messenger cache invalidation after rotation, at both the `MessengerFactory` layer and the public `OutboundRuntime.invalidate_inbox_credentials()` wrapper hosts are told to call.
- `X-Wappa-Inbox-ID` handling on non-webhook routes: a valid header binding context, an unknown Inbox rejected `404`, a malformed value rejected `400`, an absent header with no default rejected `400`, and a raising credential store answering `503` rather than `404`.
- Inbox context does not leak between requests handled by the same worker.
- The router exposes only the canonical processing, verification, and status routes, so the `{platform}` parameter cannot host a second live callback shape.

Run and record:

```bash
uv run ruff check .
uv run mypy wappa
uv run pytest -q
git diff --check
```

The implementation review must also search the live code, public docs, examples, and tests for `/webhook/inboxes/{inbox_id}`. Historical ADRs may describe the removed contract only when they link to the decision that replaced it.

## Risks and controls

The largest risk is duplicate account-event work during WABA fan-out. Host handlers must already survive Meta retries; tests should prove repeated and per-Inbox delivery does not corrupt shared account state.

A second risk is a store that returns an Inbox under the wrong WABA. Each resolved Inbox still passes `validate_inbox`, and database-backed implementations should verify the Provider Account relation in the lookup query. Symphonai adds its own Owner Channel check after Wappa dispatch.

Automatic credential selection can hide stale env configuration. Forced explicit mode removes that ambiguity for Symphonai. Standalone automatic mode prints a warning when both sources exist.

A fourth risk is load amplification. One provider request can now produce many deliveries, and each one performs an Inbox validation and a Messenger construction. A store whose `validate_inbox` is uncached turns a batched or fanned-out payload into a burst of database queries. Store implementations must cache, and the deployment should watch delivery counts per request after cutover.

A fifth risk is contract drift between the two webhook families. Meta WhatsApp intake now derives Inbox from content, while `WebhookPlugin` for external non-Meta sources still takes `inbox_id` from its URL path and binds no Inbox context. Both are defensible, but the divergence is undocumented and invites a host to assume the wrong one.

## Known gaps accepted for this release

These are understood and deliberately not fixed here. Each needs its own decision rather than a silent carry-forward.

- `WebhookPlugin` external-source routes keep URL-supplied `inbox_id` and bind no Inbox context. Any code reached from that path that calls `require_inbox_context()` raises. Pre-existing, unchanged by this work, and not covered by ADR-0010.
- `parse_inbox_from_expired_key()` falls back to the literal Inbox `"wappa"` when an expired Redis key contains no separator. Harmless in a single-Inbox deployment; in a multi-Inbox deployment it runs an expiry handler against a fabricated namespace.
- Wappa provides no delivery fingerprint, so hosts carry all deduplication responsibility. See Delivery semantics.

## Implementation status

Recorded 2026-08-29 against the working tree, candidate version `0.27.0`. This section is evidence for the review, not sign-off. Exit criteria stay unchecked until the operator confirms them.

Verified by running the commands in Verification:

- `uv run ruff check .` — passes.
- `uv run mypy wappa` — passes, 336 source files.
- `uv run pytest -q` — 576 passed.
- `git diff --check` — clean.

Verified by reading the code:

- Payload-derived routing, batch splitting, WABA fan-out with sort and de-duplication, and fail-closed behavior on an unmapped Platform Account live in `wappa/core/inbound/webhook_routing.py`.
- Full-batch Dispatch Context construction before any scheduling lives in `InboundRuntime.accept_webhook_batch`.
- The removed per-Inbox route has a `404` regression test in `tests/test_webhook_auth_contract.py`.
- ADR-0001 carries a superseding banner pointing at ADR-0010.

Every item in Verification now has coverage. Notable evidence:

- `tests/test_whatsapp_payload_routing.py` — metadata and flat phone routing, conflict rejection, WABA mismatch, batch split order, and fan-out. Its store deliberately returns `("phone-2", "phone-1", "phone-2")`, so de-duplication and sorting are asserted, and an unregistered WABA raises `PlatformAccountNotRegisteredError`.
- `tests/test_multi_inbox_webhook_context.py` — isolated per-Inbox handler contexts, payload mismatch rejection, `test_invalid_later_change_schedules_none_of_the_batch` for the no-partial-dispatch guarantee, a `503` on credential-store outage, and WABA fan-out with isolated contexts.
- `tests/test_inbox_credential_store.py` — explicit mode beating a complete legacy bundle, the auto-mode `UserWarning`, Platform Account enumeration, and rotation invalidation at both the `MessengerFactory` and `OutboundRuntime` layers.
- `tests/test_db_only_inbox_boot.py` — header `400` / `404` / `503` behavior, Inbox context not leaking between requests on one worker, and the removed route staying uninterpreted by the middleware.
- `tests/test_webhook_auth_contract.py` — the live route set is pinned, the removed callbacks `404`, and the URL factory is safe without `WP_PHONE_ID`.

Remaining, and all operator-owned:

- The previous Wappa version has not been confirmed resolvable, which the cutover procedure requires before the Meta callback URL changes.
- No exercise of `wappa_miia` against this build has been performed or recorded.
- The operator review and release naming have not happened.

## Exit criteria

- [x] Wappa exposes only `/webhook/inboxes/whatsapp` for WhatsApp verification and delivery; the old route returns 404.
- [x] Phone-scoped, batched, flat-phone, and WABA-only payloads route without using environment Inbox identity.
- [x] Unknown, inactive, conflicting, and unmapped payload scopes fail before any partial batch dispatch.
- [x] Explicit host mode selects the injected store even when a complete legacy bundle exists.
- [x] Built-in and documented custom stores implement deterministic Provider Account lookup.
- [x] `generate_whatsapp_webhook_url()` works with `WP_PHONE_ID` unset and returns the canonical URL.
- [x] Health, startup logs, examples, DDD docs, architecture docs, and the public contract agree with the implementation.
- [x] The candidate version and changelog identify the webhook, credential-store, and identity-resolver breaks. No release is published by this work item.
- [x] Ruff, mypy, the full pytest suite, and `git diff --check` pass.
- [x] `X-Wappa-Inbox-ID` is documented in the public contract and the changelog, and its `400` / `404` / `503` behavior is covered by tests.
- [x] Delivery semantics are documented for hosts: at-least-once, batch splitting, and WABA fan-out multiplicity, with the host idempotency obligation stated explicitly.
- [ ] The cutover and rollback procedure is written down and the previous Wappa version is confirmed resolvable before the Meta callback URL is changed.
- [x] The `{platform}` route parameter decision is recorded, and a test pins the exact set of live routes.
- [x] Known gaps accepted for this release are listed, and none of them is a silent carry-forward.
- [ ] **The user manually confirms `wappa_miia` runs against this Wappa build with no issues.** Both Owners receive and reply on their own WhatsApp number, each conversation resolves to its own Chat with no cross-Owner leakage, outbound sends leave from the correct number, and no errors appear in the logs during the exercise. Automated tests do not satisfy this criterion.
- [ ] The user completes the requested review and names the Wappa release approved for Symphonai consumption.

## Release handoff to Symphonai

This Wappa backlog item stays in progress during operator review. After the user approves and publishes or names the release, Symphonai may update its Wappa package pin, remove its temporary local editable install, and continue Miia testing on backend port 8000 and frontend port 5173.

Until that instruction arrives, do not claim that Symphonai or `wappa_miia` has validated the released contract.
