# ADR-0010: Authenticated, payload-routed WhatsApp webhook

## Status

Accepted. Amended 2026-11-05 so Meta additions never produce `400` (see the section at the end of Decision). Amended 2026-08-30 for authenticated raw-body routing, qualified identity, WABA membership, and the final status matrix (grilling session sections 4, 5, and 9). The companion directory decision is [ADR-0011](0011-encrypted-inbox-directory.md).

## Context

Meta configures one callback URL per App, while one WABA can contain several phone-number Inboxes. Wappa's prior `/webhook/inboxes/{inbox_id}/whatsapp` route required a different callback URL per Inbox and made the URL the routing authority. That model cannot represent a multi-Inbox Meta App, and it tempted hosts to substitute the WABA ID or an environment default when a payload carried no phone number.

Routing from payload content is only safe after Wappa has authenticated the exact bytes Meta sent. The first candidate parsed JSON and consulted the credential store before any signature check, and its only signature helper used the GET verify token as the HMAC secret.

## Decision

**One callback.** Wappa exposes `GET + POST /webhook/inboxes/whatsapp`. GET compares `hub.verify_token` with `MetaApplicationConfig.whatsapp_webhook_verify_token` and returns the challenge; it never reads the App Secret or the Inbox Directory. The per-Inbox callback and the separate verify-only callback return 404 with no alias, redirect, flag, or deprecation route.

**One Meta App.** One Wappa application binds to exactly one immutable `MetaApplicationConfig` (App Secret, verify token, Graph API version, base URL), supplied explicitly or built from `META_APP_SECRET` / `WP_WEBHOOK_VERIFY_TOKEN` / `META_API_VERSION` / `META_BASE_URL`. Configuring both sources fails startup. Mounting the callback requires both secrets in every environment; there is no development bypass and no key ring of App Secrets.

**Authenticate before anything.** For every POST: read the exact body bytes once; require a well-formed `X-Hub-Signature-256: sha256=<hex>`; compute HMAC-SHA256 with the App Secret; compare in constant time; answer a generic `401` for a missing, malformed, or mismatched signature. Only after success does Wappa decode JSON and require an object root. No parsing, directory read, payload logging, or work scheduling happens before that point.

**Qualified routing.** For each `entry[].changes[]`, Wappa builds `PlatformAccountRef(whatsapp, entry[].id)` and routes in this order:

1. `value.metadata.phone_number_id`, or a flat `value.phone_number_id`, becomes `InboxRef(whatsapp, phone_number_id)`. Wappa resolves the active record and **proves the record's `PlatformAccountRef` equals `entry[].id`**; a mismatch rejects the whole callback with `400`.
2. A change without a phone number fans out to every validated active member of the Platform Account index (sorted, duplicate-free). A stale, inactive, missing, or wrongly assigned member triggers one synchronous source reload and index repair; a failed repair answers `503` and dispatches nothing. A confirmed empty WABA answers `400`.

`entry[].id` is never an Inbox. Wappa never selects a first or default Inbox.

**All-or-nothing admission.** Wappa splits every entry and change, resolves every `InboxRef`, proves every membership relation, and builds every Dispatch Context before scheduling any delivery. Item N failing schedules none of items 1..N-1. Build-phase identity is bound and reset per item so logs are attributed correctly. Delivery stays at least once; Wappa invents no delivery fingerprint.

**Status matrix.**

| Condition | Status |
| --- | ---: |
| Missing, malformed, or invalid Meta POST signature | 401 |
| Invalid GET verify token | 403 |
| Malformed JSON or non-object root | 400 |
| Invalid Inbox identifier format in the authenticated payload | 400 |
| Confirmed unknown or inactive payload Inbox | 400 |
| Inbox and WABA membership mismatch | 400 |
| Confirmed WABA with no active Inboxes | 400 |
| Other structurally unroutable authenticated payload | 400 |
| Authenticated, routable payload with unmodelled fields or an unmodelled webhook field | 200 (processed, or `SystemWebhook(UNSUPPORTED_EVENT)`) plus a `META_SCHEMA_DRIFT` log |
| Directory, cache, source, decrypt, or runtime dependency unavailable | 503 |
| Unexpected Wappa defect | 500 |

An authenticated unknown payload Inbox is `400`, not `401`: authentication already succeeded.

The route keeps a `{platform}` path parameter; the controller accepts only WhatsApp and answers `400` for every other `PlatformType`. A test pins the live route set.

### Amended 2026-11-05: Meta additions are tolerated and reported

On 2026-11-05 a status webhook carried a new `pricing.subtype: "free_tier"`. The strict model (`extra="forbid"`) rejected it, Wappa answered `400`, and the delivery status was dropped 30 times. Meta also sent an `account_update` field Wappa did not model, and Wappa answered `400` "Unknown webhook field". Meta retries non-200 deliveries and can stop delivering to an endpoint that keeps failing, so strictness turned an additive Meta change into data loss. Instagram already mapped unknown change fields to `SystemWebhook(UNSUPPORTED_EVENT)`, so the `400` also broke the parity required by [ADR-0016](0016-one-messenger-method-per-action.md).

1. Models that parse data from Meta (webhook payloads, and Graph API responses) use `extra="allow"`. After parsing, `wappa.webhooks.core.schema_drift.report_schema_drift` logs `META_SCHEMA_DRIFT platform=<p> field=<Model.field>` once per field per process and never logs the value, which may be personal data. The event is processed and Meta gets `200`.
2. `WAPPA_STRICT_META_SCHEMA=1` turns drift into `MetaSchemaDriftError`. Wappa's own test suite sets it, so fixture drift fails CI. When the log shows drift in production, model the field and add a fixture.
3. A WhatsApp `field` that Wappa does not model and the Host did not register with `register_webhook_field` becomes `SystemWebhook(UNSUPPORTED_EVENT)` with `event_detail.platform_event = {"field", "value"}` and a drift log, answered `200`, the same as Instagram. It was `400`.
4. Unchanged: a wrong type or format in a modelled field is still an error; authentication failures are `401`; unroutable payloads (unknown or inactive Inbox, WABA mismatch, malformed JSON) keep the table above. Wappa's own output contracts (Universal Webhooks, `SystemEventDetail`, domain models) and Host inputs (REST bodies, `IMessenger` arguments) stay `extra="forbid"`. Hosts never see extras, so ADR-0016 rule 5 holds.

`400` therefore never means "Meta added a field". It means the payload cannot be routed or is malformed, which a retry cannot fix and an additive Meta change cannot cause. The `WHATSAPP_WEBHOOK_CONTRACT_DRIFT` critical log on `extra_forbidden` is removed.

## Consequences

- Meta needs one callback URL regardless of the number of registered Inboxes, and every environment that mounts it holds the App Secret.
- Hosts in explicit mode supply an `IInboxDirectorySource`; Wappa owns the reverse index and its repair. Hosts must call `refresh_inbox` after onboarding, rotation, WABA reassignment, and deactivation because a valid index cannot detect an omitted member.
- Local tests and webhook tools must sign exact request bytes with a development App Secret.
- Delivery is at least once and three multipliers can repeat one Platform event: Meta retries, batch splitting, and WABA fan-out. Account-scoped handlers must be idempotent on Platform-supplied identifiers.
- Rolling back is a two-system operation: the Wappa version and the Meta callback URL must revert together.
- `InboxRoutingMode` has exactly two values, `legacy` and `explicit`, and they are mutually exclusive: there is no `auto` mode, no precedence rule, and no fallback from one authority to the other. A process configured for one mode never consults the other's credential source.

## Alternatives considered

1. Keep one callback URL per Inbox. Rejected because Meta Apps expose one callback configuration.
2. Treat `entry[].id` as the Inbox. Rejected because it is the WABA and may group several phone numbers.
3. Choose the first Inbox under a WABA. Rejected because ordering is not business authority.
4. Preserve the old route as an alias. Rejected because two routing authorities would let hosts keep the unsafe model.
5. Trust the payload because it arrived on the public route, or verify with the GET verify token. Rejected: only the App Secret proves origin, and the verify token is a different credential.
6. Try several App Secrets or pick one from payload contents. Rejected: the payload is untrusted until verified, so it cannot select its own verification secret.
7. Skip the WABA membership check when the phone Inbox is active. Rejected: a payload could pair a known Inbox with the wrong account.
