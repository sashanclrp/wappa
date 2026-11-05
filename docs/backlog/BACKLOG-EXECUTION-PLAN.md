# Backlog execution plan

This file orders active Wappa backlog work. Individual PRDs remain the implementation source of truth for their scope, design, and exit criteria.

## In progress

1. [`260829-wappa-v0.27.0/`](./in_progress/260829-wappa-v0.27.0/plan.md): Wappa v0.27.0 multi-Inbox hardening — one authenticated payload-routed callback, qualified `InboxRef` identity, the Wappa-owned encrypted Inbox Directory, `legacy`/`explicit` routing modes, and the closed public contract. The local `v0.27.0` tag exists; the series remains open only for Symphonai adoption, PyPI verification, and the Meta callback cutover.

2. [`261103-instagram-conversations/`](./in_progress/261103-instagram-conversations/plan.md): Complete Instagram conversations and public comment primitives, formalize trusted extension access, then verify Unified Login and Symphonai integration. Includes DDD/public-contract improvements, developer skill packages and Meta use-case setup guidance. The text/seen/echo baseline exists; remaining PRDs and live/skill gates stay open. Its own dependency graph governs execution; unrelated v0.27 external clocks do not block offline Instagram work.

## Pending

No ordered items.

## Drafts

- [`provider-delivery-identity.md`](./drafts/provider-delivery-identity.md): provider-aware delivery identity and idempotency, deferred until an adapter provides stable provider evidence.

- [`261105-mid-send-reaction-core-method.md`](./drafts/261105-mid-send-reaction-core-method.md): `send_reaction(message_id, emoji, target)` as a core Messenger method (ADR-0016 known gap); no Platform sends reactions and inbound Instagram reactions are dropped today.

- [`261105-mid-inbox-connector-contract.md`](./drafts/261105-mid-inbox-connector-contract.md): account connection (WhatsApp Embedded Signup, Instagram, Telegram bot token) as its own Inbox Connector contract, not an `IMessenger` capability (ADR-0016 known gap; needs its own ADR before building).

- [`ideas.md`](./drafts/ideas.md): Unordered ideas that are not ready for implementation.
