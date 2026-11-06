---
checked_on: 2026-11-06
checked_against: Wappa 0.34 code (wappa/domain/interfaces/template_messaging.py, wappa/messaging/whatsapp/platform_messenger.py, wappa/schemas/core/recipient.py, wappa/messaging/whatsapp/errors.py, wappa/messaging/outbound_runtime.py) and Meta WhatsApp Cloud API pages (Graph v26.0)
revision: 1
---

# WhatsApp-only features

## Contents

- What WhatsApp adds to a message
- Addressing: phone and BSUID
- The 24-hour window and Templates
- Location and phone-number requests
- Flows and calls (inbound only)

Everything shared (text, media, interactive, results) is in `messaging.md`. This file covers only what `self.whatsapp` adds, and what WhatsApp sends that Instagram doesn't. `self.whatsapp` is a `WhatsAppMessenger` (`from wappa.messaging.whatsapp import WhatsAppMessenger`, for annotations only). It is set in a WhatsApp dispatch and `None` elsewhere, so guard every use with `if self.whatsapp:`.

## What WhatsApp adds to a message

`webhook.user` carries the phone (`wa_id`) and/or the BSUID (business-scoped user ID) Meta sent. Read them directly, and build replies with `webhook.user.delivery_addresses()`, never from one field. `webhook.entry_referral` carries click-to-WhatsApp ad context (`webhook.is_from_ad()`). Coexistence numbers (also on the WhatsApp Business app) add `process_outbound_echo` (origin `BUSINESS_APP`: a human replied from the phone), `process_history_sync`, and `process_inbox_connection` (`account_offboarded` / `account_reconnected`).

## Addressing: phone and BSUID

A `DirectMessage` carries every Delivery Address the webhook had. WhatsApp sends to the phone first, then the BSUID, and falls back to the next address only when Meta rejects the address itself (131030, or 131062 mapped to `error_code="BSUID_RECIPIENT_NOT_SUPPORTED"`). Window (131047) and rate-limit (131056) errors never fall back. `result.attempted_recipients` lists what was tried. Authentication Templates go to phones only. Never pick an address yourself, and don't add a BSUID-to-phone fallback middleware: Wappa already does it.

## The 24-hour window and Templates

A free-form send works only within 24 hours of the User's last message. Outside it, Meta rejects with 131047 (a `REJECTED` result), and only an approved Template can open the conversation. Wappa has **no window guard**: track the User's last inbound time yourself (a Host middleware or a check before a scheduled send) if you want to choose a Template up front.

```python
if self.whatsapp:
    result = await self.whatsapp.templates.send_text_template(
        "order_confirmed", target, body_parameters=[{"type": "text", "text": order_no}],
        language_code="en_US", template_type="utility",
    )
```

`self.whatsapp.templates` (`ITemplateMessaging`) has `send_text_template`, `send_media_template(..., media_type, media_id=None, media_url=None, ...)` and `send_location_template(..., latitude, longitude, name, address, ...)`. `template_type` is required (for example `"marketing"`, `"utility"`, `"authentication"`). `routing_policy="category_default"` (the default) or `"cloud_messages_fallback"` chooses the endpoint. There is no `send_template` and no `override=`. Outside a dispatch (jobs, campaigns), use `OutboundRuntime.from_app(app).templates(inbox_ref)`. It returns `REJECTED` with `error_code="capability_unsupported"` on a Platform without Templates. The HTTP Template routes are off by default (`Wappa(include_template_transport_api=True)`).

Instagram has no Templates: outside its window there is no way to start the conversation, so wait for the User to write. Its messaging window is 24 hours from the User's last message, plus 7 days for a single private reply to a comment (`10/2534022` outside it). Template creation and approval happen in Meta's WhatsApp Manager, not in Wappa.

## Location and phone-number requests

```python
if self.whatsapp:
    await self.whatsapp.send_location_request("Share your location for delivery", target)
    await self.whatsapp.send_contact_request("Share your phone so we can call you", target)
else:
    await self.messenger.send_text("Type your city, please", target=target)
```

The answers arrive in `process_message` as a location or contact message. Instagram can't return a location or phone from a prompt, so ask the User to type it there.

## Flows and calls (inbound only)

- **Flows.** A completed WhatsApp Flow arrives in `process_message`: `webhook.message.is_flow_reply`, and `webhook.message.interactive.nfm_reply` (`name`, `body`, `response`, `flow_token`); `get_interactive_selection()` returns the `flow_token`. Wappa has no method to send a Flow. Don't invent `send_flow`.
- **Calls.** Call events arrive in `process_call` (`CallWebhook`: `call_id`, `event`, `direction`, `status`, `duration`, `phone_number`, `bsuid`). Wappa can't place or answer calls.
