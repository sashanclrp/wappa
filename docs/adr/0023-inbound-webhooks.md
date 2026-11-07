# Inbound webhooks: authenticate, route, admit, translate, dispatch

Accepted, 2026-11-06. Consolidates the inbound decisions first recorded for the Inbound Runtime and Dispatch Context (undated), the authenticated payload-routed callback (2026-08-30, amended 2026-11-05 for schema drift), Inbox-independent External Webhooks (2026-09-13), the echo filter (2026-11-05) and the architecture-hardening Platform Registry (2026-11-06). This ADR states the whole current decision; the earlier ADRs it absorbed were deleted.

## Context

Meta configures one callback URL per App and per product, while one WABA holds several phone-number Inboxes, so the URL cannot be the routing authority. Routing from payload content is safe only after Wappa has authenticated the exact bytes Meta sent. Translation must stay pure so Platform adapters are testable and cannot drift into runtime orchestration. Before the hardening the Platform was re-decided in five shared places against three disagreeing supported-Platform lists, and an uninstalled Platform answered Meta's GET challenge.

## Decision

### Names and responsibilities

1. **Inbound Runtime** turns an accepted Platform webhook into a context-bound handler dispatch. **Dispatch Context** is the per-event bundle: `InboxRef`, User, Messenger, Cache Factory, optional DB factories, SSE identity and the cloned `WappaEventHandler`. A **Processor** only translates a Platform payload into a **Universal Model** (`InboundMessageWebhook`, `StatusWebhook`, ...): it never mutates ContextVars, builds Messengers, resolves caches or clones handlers. Universal Models are Pydantic schemas with one canonical home. No compatibility shims for old import paths.
2. **`PlatformWebhooks` is the inbound seam** (`wappa/core/inbound/platform_webhooks.py`): `platform`, `builtin_fields`, `async route(payload, resolver) -> tuple[RoutedWebhookDelivery, ...]` (may do credential I/O) and `async translate(payload, *, inbox_id) -> UniversalWebhook` (pure; `inbox_id`, the routed Inbox, is a required keyword on every adapter, with no adapter-side default). `route` and `translate` stay separate because admission and echo proof run between them. Message-type tables stay private to each adapter.
3. **The Platform Registry is the composition root.** `wappa/platforms/` builds `PLATFORMS: Mapping[PlatformType, PlatformEntry]` (the `PlatformWebhooks` adapter, the Messenger builder, a display name) with `build_platforms(field_registry)`; each built app holds its own table on `app.state.platforms`, and every shared reader (webhook controller, `/webhook/platforms`, Messenger factory, `/api/{platform}` validation, core plugin) reads that table. `PlatformType` is vocabulary, not installation: a member with no entry (Telegram, Teams) is reserved, answers `400` on the callback (GET and POST) and raises in code, never falls through to WhatsApp. Platform-specific imports and branches are legitimate only in the registry and adapter folders.

### The callback

4. **One callback per Platform:** `GET + POST /webhook/inboxes/{platform}` (`whatsapp`, `instagram`). GET compares `hub.verify_token` with `MetaApplicationConfig.whatsapp_webhook_verify_token` and returns the challenge; it never reads the App Secret or the Inbox Directory. Per-Inbox callback URLs return 404 with no alias.
5. **One Meta App per Wappa application.** One immutable `MetaApplicationConfig` (App Secret, verify token, Graph API version, base URL), explicit or from `META_APP_SECRET` / `WP_WEBHOOK_VERIFY_TOKEN` / `META_API_VERSION` / `META_BASE_URL`; both sources at once fail startup; mounting the callback requires both secrets in every environment.
6. **Authenticate before anything.** Read the exact body once, require `X-Hub-Signature-256: sha256=<hex>`, HMAC-SHA256 with the App Secret, constant-time compare, generic `401` on failure. Only then decode JSON and require an object root. Callback authentication stays in the controller (`MetaCallbackAuthenticator`) and is not a `PlatformWebhooks` member while every Platform is a Meta callback; a non-Meta Platform adds `authenticate` then.
7. **Qualified routing.** WhatsApp: `value.metadata.phone_number_id` becomes `InboxRef(whatsapp, …)` and the record's `PlatformAccountRef` must equal `entry[].id` (mismatch rejects the whole callback with `400`); a change without a phone number fans out to every validated active member of the account index, with one synchronous repair on a stale member (`503` if it fails, `400` for a confirmed empty WABA). `entry[].id` is never an Inbox and Wappa never picks a first or default Inbox. Instagram: each event must address its professional account, which is the Inbox.
8. **All-or-nothing admission.** Every entry and change is split, resolved, proved and built into a Dispatch Context before any delivery is scheduled. Delivery is at least once; Wappa invents no fingerprint.
9. **Meta additions are tolerated and reported.** Models that parse Meta data use `extra="allow"`; `report_schema_drift` logs `META_SCHEMA_DRIFT platform=<p> field=<Model.field>` once per field per process without the value, and Meta gets `200`. `WAPPA_STRICT_META_SCHEMA=1` (set in Wappa's own tests) turns drift into an error. An unmodelled change field the Host did not register becomes `SystemWebhook(UNSUPPORTED_EVENT)` on both Platforms. Wappa's own output contracts and Host inputs stay `extra="forbid"`.
10. **Status matrix.**

| Condition | Status |
| --- | ---: |
| Missing, malformed or invalid POST signature | 401 |
| Invalid GET verify token | 403 |
| Uninstalled Platform (GET or POST), malformed JSON, non-object root, invalid Inbox ID format, unknown or inactive Inbox (except `account_reconnected`, [ADR-0032](0032-inactive-inbox-reconnect.md)), Inbox/account mismatch, confirmed empty account, other unroutable payload | 400 |
| Authenticated routable payload with unmodelled fields or field | 200 plus `META_SCHEMA_DRIFT` |
| Directory, cache, source, decrypt or runtime dependency unavailable | 503 |
| Unexpected Wappa defect | 500 |

### Extensions, echoes and identity evidence

11. **Extension fields share the callback.** A Host registers a field it owns with `register_webhook_field(..., platform=...)`, where `platform` is required (no WhatsApp default); its parser and handler own the schema, and it enters through the same signature and admission boundary. Each adapter's `builtin_fields` are reserved.
12. **Wappa fixes the meaning of the echo lane.** `OutboundEchoWebhook` only ever carries messages not sent through a Wappa Messenger. Platform evidence first (WhatsApp Coexistence echoes are `BUSINESS_APP`); without evidence (Instagram) Wappa keeps `ISentMessageRegistry`, one ten-minute Table Cache key per message it sent, claimed by the echo (two-minute grace after the claim) and re-checked after 1 s and 2 s. A registry outage delivers the echo with `origin=UNKNOWN`, never drops it. Hosts own persistence.
13. **SSE identity comes from evidence fields** (`UserBase`, `CallWebhook`, `StatusWebhook.recipient_bsuid` / `recipient_phone_id`), never from a Platform check or identifier shape.
14. **External Webhook Sources are Inbox-independent.** Their callbacks are ID-less by default; a plugin's dynamic Webhook ID never identifies or authorizes an Inbox, and `ExternalEvent` carries no Inbox or User. A Host may attach an `IExternalWebhookContextResolver` that returns an `InboxRef` (and optional User) after the processor authenticates, or `None` for database-only dispatch.

## Consequences

- Meta needs one callback URL per Platform regardless of Inbox count. Local tools sign exact bytes with a development App Secret.
- Three multipliers can repeat one Platform event (Meta retries, batch splitting, WABA fan-out), so account-scoped handlers are idempotent on Platform IDs.
- A third Platform touches its adapter folders, one `PlatformEntry`, one `PlatformType` member and one record pair; `tests/test_third_platform_contract.py` proves it with a fake Platform defined only in the test and guards shared code against new Platform branches.
- Every Instagram send makes one short-lived registry write; a human message from the Instagram app reaches the Host about 3 s late. The registry is shared across processes only on Redis.
- Rolling back the callback is a two-system operation: the Wappa version and the Meta callback URL revert together.

## Alternatives rejected

- One callback URL per Inbox; treating `entry[].id` as an Inbox; choosing a first Inbox under a WABA; an alias for the old route.
- Trusting the payload because it arrived on the route, verifying with the GET verify token, or trying several App Secrets.
- Letting Processors mutate runtime context; "Webhook Service" or "Request Context" as the orchestration name.
- Strict `extra="forbid"` on Meta input (turned an additive Meta change into data loss).
- Delivering every Instagram echo for Hosts to filter, or Wappa storing conversation history to filter.
- Optional Inbox identity on `ExternalEvent` (keeps the category error).
- A per-Platform authenticator now (a one-adapter seam while both Platforms are Meta).
