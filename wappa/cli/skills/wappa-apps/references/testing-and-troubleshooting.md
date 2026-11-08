---
checked_on: 2026-11-06
checked_against: Meta WhatsApp Cloud API and Instagram messaging error codes (Graph v26.0) and live Gate A runs of 2026-11-05 and 2026-11-06
revision: 1
---

# Testing and troubleshooting

## Contents

- Evidence rules
- Offline tests
- Live checklist
- Troubleshooting

## Evidence rules

Keep these facts separate:

- Callback acknowledgement (HTTP 200 from your server).
- Provider acceptance (a `message_id` came back).
- Echo and `read` events.
- What the recipient actually saw.

A mocked test never stands in for live proof. Never paste tokens, authorization codes, verify tokens or real User IDs into tests, logs or docs. Use placeholders.

## Offline tests

- **Handler logic, any Platform.** The fastest path is a recording `IMessenger` fake (implement `platform`, `inbox_id`, `supported_operations`, `resolve_platform_user_profile` and the sends you use) plus Wappa's real memory cache (`create_cache_factory("memory")(inbox_id=ref.cache_namespace, user_id=...)`), bound with `handler.with_context(...)`. Run the same test once per Platform `InboxRef`; a shared action must pass both unchanged.
- **Handler logic against Instagram's real adapter.** Build `InstagramMessengerAdapter` against `httpx.MockTransport`, then bind your handler with `handler.with_context(inbox_id=..., user_id=..., messenger=MessengerPipeline(raw), cache_factory=create_cache_factory("memory")(inbox_id=ref.cache_namespace, user_id=...), inbox_ref=ref)`. `with_context` builds `self.instagram` from that Messenger, so comment and content calls in the handler run against the same mock.
- **Webhooks.** Feed payloads through the Platform's processor (`await InstagramWebhookProcessor().translate(payload)`, and the WhatsApp processor likewise), using the shapes from Meta's webhook examples. Set `SYSTEM_STRICT_META_SCHEMA=1` in tests so a payload drifting from Wappa's schema fails loudly.
- **Signed HTTP.** Sign bodies with `MetaCallbackAuthenticator(secret).sign(body)` and POST them to `/webhook/inboxes/<platform>`.
- **What to assert.** Wire JSON, the target `recipient` (`id` or `comment_id`), one dispatch per event, and no call for own comments or echoes.

## Live checklist

1. GET verify returns 200; app fields are ticked; account `subscribed_apps` lists the fields.
2. Text round trip on each Platform: one reply, and a `read` reaches `process_status`. On Instagram, a message you send from the Instagram app reaches `process_outbound_echo` (not `process_message`); Wappa's own sends never echo.
3. Each media family in both directions, using the unified kit in `media-formats.md`; each interactive form (`send_button_message`, `send_list_message`, `send_cta_message`, `send_carousel`), with quick replies and postbacks reaching `process_message` via `get_interactive_selection()`.
4. A comment gets a public reply, a private reply, then a DM follow-up after the User answers. Test hide/unhide/delete and enable/disable on disposable media. A mention reaches `process_mention`.
5. Two Users at the same time, and the same person on two connected accounts: state never crosses.
6. Self-service login: connect, replay (expect 400), cancel, reconnect (version + 1), revoke (inactive).

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `.env` change ignored | The reloader does not watch `.env`; restart. |
| Reply loop | Not ignoring `is_own_comment`, or treating echoes as messages. |
| An Instagram send succeeded but the User saw nothing | Instagram has no `failed` status. Check the format against `media-formats.md` (an HEVC link, for example), and confirm on the device. |
| `131047` (WhatsApp) | Outside the 24-hour window. Send an approved Template (`whatsapp.md`). |
| `131030` (WhatsApp) | The address was rejected (a test number's allow-list, or no WhatsApp account). Wappa already tried every Delivery Address. |
| `131053` (WhatsApp) | Meta couldn't use the media. Wappa refuses the known cases before any call; an extension-less URL or a Media ID isn't checked. |
| `ValueError` before any send | A limit or a media rule: read the message, fix the input (`media-formats.md`, `messaging.md`). Never catch and ignore it. |
| `rate_limited` / HTTP 429 | A long Meta limit; try after `retry_after`. Instagram's code `4` covers the whole app. |
| `10/2534022` | Instagram: outside the messaging window. Wait for the User; private replies have their own window. |
| `100/2534025` | Comment already privately replied to, expired, or ineligible. |
| `100/2534014` | Recipient is not an IGSID for this account. Never use usernames or another Inbox's IDs. |
| `UnsupportedOperationError` | The operation or option has no Instagram equivalent; check `supported_operations`. |
| `TargetInboxMismatchError` | The target or reference belongs to another Inbox; build it from this handler's `inbox_ref`. |
| Attachment `not_found` | The CDN URL expired; download on receipt. |
