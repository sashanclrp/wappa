# Backlog execution plan

This file orders active Wappa backlog work and lists every top-level item in the drafts, pending and in_progress folders. Individual PRDs remain the implementation source of truth for their scope, design, and exit criteria. When an item ships, delete it and regenerate this file (see [README.md](./README.md)).

## In progress

1. [260829-wappa-v0.27.0/](./in_progress/260829-wappa-v0.27.0/plan.md): Wappa v0.27.0 multi-Inbox hardening — one authenticated payload-routed callback, qualified `InboxRef` identity, the Wappa-owned encrypted Inbox Directory, `legacy`/`explicit` routing modes, and the closed public contract. Released; the series remains open only for Symphonai adoption, PyPI verification, and the Meta callback cutover.

2. [261103-instagram-conversations/](./in_progress/261103-instagram-conversations/plan.md): Instagram conversations, public comment primitives, Unified Login connection lifecycle, Symphonai adoption and developer skills. PRDs I01–I08 are implemented and offline-tested; live gates (A conversations, B Unified Login, C Symphonai) and skill evidence stay open, recorded in [tests/live-test-plan.md](./in_progress/261103-instagram-conversations/tests/live-test-plan.md). Its own dependency graph governs execution; unrelated v0.27 external clocks do not block it.

3. [261105-mid-inbox-connector-contract.md](./in_progress/261105-mid-inbox-connector-contract.md): the Inbox Connector contract. `IInboxConnector`, `InstagramConnector` and `WhatsAppConnector` already exist (ADR-0017); remaining work is the live check of both connectors, Symphonai's switch to `WhatsAppConnector`, a credential-step result for non-OAuth Platforms, and optional phone-number registration.

4. [261106-architecture-hardening/](./in_progress/261106-architecture-hardening/plan.md): finish hardening Wappa as multi-Inbox and multi-Platform. Ten verified area audits feed a 33-item backlog in dependency order (neutral contract types, dead-seam deletions, the `PlatformWebhooks` registry, one media seam, the capability extension mechanism, connection typing) plus five ADR drafts and the third-Platform contract test. It waits on the review checkpoint before any code change.

## Pending

No ordered items.

## Drafts

Unordered. Each needs a design pass before it can move to pending.

- [260414-whatsapp-template-management-and-template-webhooks.md](./drafts/260414-whatsapp-template-management-and-template-webhooks.md): WhatsApp Template CRUD against the Graph API and typed Template lifecycle webhooks (`message_template_status_update`); today Hosts can only receive these through `register_webhook_field`.

- [261105-low-conversation-entry-points-capability.md](./drafts/261105-low-conversation-entry-points-capability.md): `IConversationEntryPoints` — conversation starters, commands/persistent menu and welcome message as one capability across Platforms.

- [261105-low-profile-reader-capability.md](./drafts/261105-low-profile-reader-capability.md): `IProfileReader` — read the connected Inbox's own business profile in one shape on every Platform.

- [261105-mid-commerce-capability.md](./drafts/261105-mid-commerce-capability.md): product messages homologated across Platforms (WhatsApp catalog messages, Instagram product templates); placement and product identity still open.

- [261105-mid-send-reaction-core-method.md](./drafts/261105-mid-send-reaction-core-method.md): `send_reaction(message_id, emoji, target)` as a core Messenger method (ADR-0016 known gap). No Platform sends reactions yet; inbound reactions already arrive typed on both Platforms.

- [261105-mid-whatsapp-calling-prd.md](./drafts/261105-mid-whatsapp-calling-prd.md): WhatsApp Business Calling — an `ICallControls` capability (accept, reject, terminate, outbound calls, call permission) on top of the existing `CallWebhook`.

- [261106-low-whatsapp-first-remaining-gaps.md](./drafts/261106-low-whatsapp-first-remaining-gaps.md): the WhatsApp-first sweep's open gaps — reaction sends (with the open decision on Instagram's heart-only reactions), the WhatsApp interactive types Wappa does not offer (flow, voice call, catalog, product, address), and send status plus Template parameters Wappa drops.

- [261106-mid-media-adaptation-service.md](./drafts/261106-mid-media-adaptation-service.md): Media Adaptation — a Platform-neutral engine that detects real media types and adapts media to each Platform's `MediaSpec` (transcode, resize, video poster frame, sticker and voice-note formats), runs off the event loop with a content-hash cache, and serves short-lived Wappa-hosted public URLs where a Platform needs one; optional `wappa[media]` extra, off by default.

- [261105-mid-whatsapp-flows-prd.md](./drafts/261105-mid-whatsapp-flows-prd.md): WhatsApp Flows — an `IFlowMessaging` capability to send Flows and a typed `nfm_reply` on receive; data exchange and management in a later phase.

- [provider-delivery-identity.md](./drafts/provider-delivery-identity.md): provider-aware delivery identity and idempotency, deferred until an adapter provides stable provider evidence.

- [ideas.md](./drafts/ideas.md): unordered ideas that are not ready for implementation.
