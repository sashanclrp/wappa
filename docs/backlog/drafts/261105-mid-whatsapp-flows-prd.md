---
status: draft
origin: ADR-0016 contract map (2026-11-05): WhatsApp-only capability
---

# PRD (draft): WhatsApp Flows in Wappa

## Problem

WhatsApp Flows are multi-screen native forms (JSON-defined screens with inputs, dropdowns, date pickers, and so on) that open inside WhatsApp. They are the best intake UX on WhatsApp, but Wappa can neither send nor receive them. Today a Host has to call the Graph API itself and parse `nfm_reply` payloads by hand.

## Scope

1. **Send:** an `IFlowMessaging` capability (WhatsApp-only per ADR-0016): `send_flow(target, flow_id | flow_name, cta, body, header?, footer?, mode: draft|published, flow_action: navigate|data_exchange, screen?, data?, flow_token)`. It is reachable via `messenger.require_capability(IFlowMessaging)` and runs through the pipeline so middleware sees it.
2. **Receive:** a completed Flow arrives as `InboundMessageWebhook` with an interactive `nfm_reply`. Wappa exposes the decoded `response_json`, the `flow_token` and the Flow name in a typed message (`get_interactive_selection()` returns the `flow_token`).
3. **Data exchange endpoint (optional, phase 2):** Flows with `data_exchange` call the Host's endpoint with encrypted payloads (RSA + AES-GCM). Wappa provides the crypto and request/response models; the Host owns the business logic.
4. **Management (phase 2):** list, create, update JSON, publish and deprecate Flows (`/{waba}/flows`), behind a separate admin capability. This is not a Messenger concern.

## Out of scope

- A Flow JSON builder or UI.
- Instagram equivalents: none exist. Instagram keeps using `send_list_message` / buttons and Scores.

## Open questions

- Should Template-launched Flows (a Flow button inside a Template) live on `ITemplateMessaging` or `IFlowMessaging`?
- Key management for data exchange: does Wappa store the business private key, or does the Host inject it?

## Exit criteria

- Send and receive a published Flow live; the decoded response reaches `process_message`.
- Data-exchange crypto has unit tests against Meta's sample vectors.
