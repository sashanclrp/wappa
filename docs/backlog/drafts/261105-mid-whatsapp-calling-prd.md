---
status: draft
origin: ADR-0025 contract map (2026-11-05): WhatsApp-only capability
last_reviewed: 2026-11-06
---

# PRD (draft): WhatsApp Business Calling in Wappa

## Code reality (2026-11-06)

CallWebhook and call-permission reply parsing exist. Call controls, calling settings and the live call/permission gates remain unimplemented. The architecture plan names this capability as future work; it does not absorb this PRD.

## Problem

The WhatsApp Business Calling API lets Users call the business, and the business call Users who granted permission, with WebRTC media handled by the business. Wappa already parses inbound call webhooks (`CallWebhook`) but has no way to act on a call: no accept, reject, terminate, outbound call or call-permission request.

## Scope

1. **`ICallControls` capability (WhatsApp-only per ADR-0025):**
   - `pre_accept(call_id, sdp_answer)`, `accept(call_id, sdp_answer)`, `reject(call_id)`, `terminate(call_id)`.
   - `start_call(target, sdp_offer)` for business-initiated calls.
   - `request_call_permission(target, body)`, which is also how a User grants permission.
   - Results use `OperationOutcome`, like other capabilities.
2. **Inbound:** `CallWebhook` covers connect, terminate and status; call-permission replies arrive as interactive selections (`call_permission_reply` already exists in `InteractiveType`). Validate that both arrive in one shape.
3. **Settings:** enable calling, set the call icon visibility and business hours (`/{phone_number_id}/settings`). These go behind a separate admin capability, not the Messenger.
4. **Media:** WebRTC/SDP negotiation and audio bridging stay Host-owned (or an extension, for example a SIP or voice-agent bridge). Wappa only carries SDP strings.

## Out of scope

- Running a media server or voice AI inside Wappa.
- Instagram calling (no API).

## Open questions

- Should SIP-based calling (Meta's SIP option) be modelled alongside WebRTC?
- Call event ordering and idempotency: which events guarantee a terminal state for Host cleanup?

## Exit criteria

- A User-initiated call can be pre-accepted, accepted and terminated live through `ICallControls`, with events reaching the handler.
- Call permission request and grant work live.
