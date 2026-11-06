---
status: draft
origin: ADR-0025 contract map (2026-11-05)
last_reviewed: 2026-11-06
---

# Commerce: product messages homologated across Platforms

## Code reality (2026-11-06)

No shared commerce sending capability has landed. Existing carousel/card sends and inbound order models do not satisfy the product/catalog send contract or its live acceptance gates. Architecture hardening does not absorb this scope.

Wappa has no commerce support yet. Sending products is an action several Platforms share, so by [ADR-0025](../../adr/0025-messenger-contract.md) it gets one Platform-neutral shape, adapted per Platform. It is not a WhatsApp-only feature.

## Native options

| Platform | Native | Wappa mapping (proposed) |
| --- | --- | --- |
| WhatsApp | catalog messages: single product (`product`), multi-product (`product_list`, ≤ 30 items in ≤ 10 sections), catalog message; order webhooks (`order`) | native |
| Instagram | product template (`template_type: product`, items from a connected catalog); generic template cards as a fallback | product template, or cards (image, title, price, "View" URL / "Buy" button) built from the same product data |
| Telegram | invoices and payments; otherwise photo cards | later |

## Open design questions (discuss before building)

- **Placement:** add `send_product` / `send_product_list` to `IMessenger` (core, adapted), or make it an `ICommerceMessaging` capability that every commerce-ready Platform implements? Lean: a shared capability, because it needs a catalog connected to the Inbox, which not every Inbox has.
- **Product identity:** WhatsApp uses `catalog_id` + `product_retailer_id`; Instagram uses catalog product IDs. A neutral `ProductRef(catalog_id, product_id)` looks right.
- **Inbound:** WhatsApp `order` messages, plus cart and checkout events, need one Universal shape (an order selection on `InboundMessageWebhook`, or its own type).
- **Fallback:** when no catalog is connected, should Wappa render cards from Host-supplied product data, or reject?

## Exit criteria

- One contract (method or shared capability) with WhatsApp and Instagram adapters, tests and live evidence.
- Inbound orders in one Universal shape.
