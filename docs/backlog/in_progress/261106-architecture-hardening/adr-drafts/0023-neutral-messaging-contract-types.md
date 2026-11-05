# Neutral messaging contract types

Status: Proposed, 2026-11-05. Draft for H-01, H-02, H-03, H-04, H-05, H-13, H-14, H-16.

## Context

ADR-0016 made `IMessenger` the one Inbox-bound send contract with one method per cross-Platform action, and ADR-0014 left the housing of `MessageResult` as a follow-up. The follow-up never happened: `MessageResult` is defined in the WhatsApp package with `platform` defaulting to WhatsApp, and `wappa.domain.results` imports it at runtime. `IMessenger.send_button_message` and `send_list_message` take WhatsApp wire models (`InteractiveHeader`, `ListSection`), so Instagram unwraps them with `getattr` and Hosts build WhatsApp image dicts for Instagram. `mark_as_read` declares its target optional although Instagram requires it and the shipped examples omit it. The neutral inbound type carries a WhatsApp-only `.whatsapp` sender slot, and the domain `PrivateReply` validator names Instagram. `capability()` is implemented twice with different semantics.

## Decision

1. Neutral send values live under `wappa/domain/` only. `MessageResult` is defined in `wappa/domain/results.py` with `platform` required and `platform_response` as the single native-evidence field; WhatsApp-specific construction lives in the WhatsApp adapter. `ButtonHeader` (text, or image by `url` or `media_id`), `ListSection` and `ListRow` live in `wappa/domain/interactive.py`, and both button and list messages take `header: ButtonHeader | None`. Platform limits (video or document headers, row counts) are adapter validation, raised before any provider call (ADR-0016 rule 3).
2. `mark_as_read(message_id, target, *, typing=False)`: the target is required on every Platform.
3. Neutral webhook and target types carry no Platform-named fields or validators. `InboundMessageWebhook.whatsapp` and `WhatsAppIncomingWebhookData` are removed; `PrivateReply` has no Platform check, and adapters without private replies reject it at send.
4. `IMessenger.capability(kind)` and `require_capability(kind)` are implemented once in the base over a `_capabilities` mapping each adapter fills in its constructor.
5. `supported_operations` stays an explicit per-adapter set; a parity test checks it against overridden methods plus declared qualifier tokens (`send_text:private_reply`), and another checks `MessengerPipeline` signatures against `IMessenger`.
6. HTTP event helpers record `result.platform`; they take no `platform` argument.

## Consequences

`wappa.domain` no longer imports any adapter, and a new Platform implements `IMessenger` without importing WhatsApp. Breaking for Hosts: `MessageResult` import path and required `platform`, header and list types, `mark_as_read` signature, `InboundMessageWebhook.whatsapp`, `dispatch_message_event`/`fire_api_event` `platform=`. No aliases; every break is listed in CHANGELOG.

## Supersedes

None fully. Completes the ADR-0014 `MessageResult` follow-up and amends the ADR-0016 contract map (signature of `mark_as_read`, header types). Banner ADR-0014 and ADR-0016 on acceptance.
