# Inbox connection: typed seam, one Meta transport, no deauthorize side door

Status: Proposed, 2026-11-05. Draft for H-28, H-29, H-30, H-31.

## Context

ADR-0017 made `IInboxConnector` the InboxConnection contract, with WhatsApp and Instagram adapters on a shared Meta login core. Three defects remain. The Instagram deauthorize route builds its own Dispatch Context, skips the Inbox Directory and makes `wappa.connections` import the webhooks layer, for a callback that Meta sends only for Instagram Login grants; Wappa's connector issues Unified Login grants only (public contract, Instagram adapter docs). The seam erases the persisted record type with `Any`, and neither adapter checks that a grant belongs to its Platform. `InstagramSubscriptions` carries a second Graph transport with hand-copied outcome classification, and both `complete()` methods repeat the same authorization prelude.

## Decision

1. The Instagram deauthorize route and `deauthorization_event` are removed. `InboxConnectionWebhook` stays fed by WhatsApp `account_offboarded`/`account_reconnected`. If Instagram Login is supported later, its parser lives in `wappa/webhooks/instagram/` and dispatches through the inbound runtime; routes only adapt HTTP.
2. `ActivationResult.record` is `ActiveInboxCredentialRecord`, `previous` is `CredentialRecord | None`, and `activate` raises `ValueError` when the grant or `InboxRef` Platform differs from the connector's, checked by one shared helper.
3. Meta Graph calls share one module-level `graph_request` function with one outcome classification; `MetaBusinessLogin.authorize(...)` is the one consume, exchange, debug, scopes prelude. The Graph version and base URL come only from `MetaApplicationConfig`. No template base class over the connectors.
4. Connectors stay Host-composed; Wappa owns no connector registry until a non-Meta connector exists.

## Consequences

Breaking: `POST /webhook/inboxes/instagram/deauthorize`, `wappa.connections.deauthorization_event` and the `InstagramSubscriptions` constructor. Unified Login revocation stays the Host's job (deactivate the record, then `disconnect`). The connector backlog draft is cut to its open Wappa items.

## Supersedes

None fully. Amends ADR-0016's contract-map `InboxConnectionWebhook` row (Instagram source removed) and ADR-0017 (typed record, Platform precondition). Banner both on acceptance.
