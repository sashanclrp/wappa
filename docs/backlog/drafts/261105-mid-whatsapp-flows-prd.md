---
status: draft
origin: ADR-0025 contract map (2026-11-05): WhatsApp-only capability
last_reviewed: 2026-11-06
---

# PRD (draft): WhatsApp Flows in Wappa

## Code reality (2026-11-06)

Architecture hardening H-25 implemented inbound FlowReply and typed nfm_reply translation, including decoded response and flow_token selection, in commit 1ae841a. Do not rebuild that slice. This draft retains outbound IFlowMessaging, pipeline integration, live published-Flow acceptance, and the unresolved phase-2 crypto/management scope.

## Problem

WhatsApp Flows are multi-screen native forms (JSON-defined screens with inputs, dropdowns, date pickers, and so on) that open inside WhatsApp. They are the best intake UX on WhatsApp, but Wappa cannot yet send them. Inbound `nfm_reply` is already typed through `FlowReply`; a Host still has to arrange the outbound Flow launch.

## Scope

1. **Send:** an `IFlowMessaging` capability (WhatsApp-only per ADR-0025): `send_flow(target, flow_id | flow_name, cta, body, header?, footer?, mode: draft|published, flow_action: navigate|data_exchange, screen?, data?, flow_token)`. It is reachable via `messenger.require_capability(IFlowMessaging)` and runs through the pipeline so middleware sees it.
2. **Receive, implemented by architecture hardening H-25:** a completed Flow arrives as `InboundMessageWebhook` with an interactive `nfm_reply`. Wappa exposes the decoded `response_json`, the `flow_token` and the Flow name in a typed message (`get_interactive_selection()` returns the `flow_token`).
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
