# One Messenger method per action, across every Platform

Accepted, 2026-11-05. Supersedes the Instagram-specific send and sender-action methods introduced in the unreleased work under ADR-0015.

Wappa's value is that a Host writes a conversation once and runs it on any connected Platform. Every new Platform therefore adapts to the existing Messenger contract and Universal Webhook shapes. It does not extend them with parallel, Platform-named methods. The first Instagram pass broke this rule: it added `mark_seen`, `set_typing`, `send_quick_replies`, `send_buttons`, `send_card` and an `InteractionWebhook` lane next to the WhatsApp-shaped methods. Hosts would then have needed `if instagram` branches (Symphonai's `mark_read` helper was the first one), and every action would have been maintained twice.

## Decision

1. **One action, one method.** When an action exists on more than one Platform, it has exactly one `IMessenger` method. Each Platform adapter maps that method onto its native API, even when the mapping takes several provider calls or loses presentation detail. Examples:
   - `mark_as_read(message_id, typing, target)` is a message read plus typing indicator on WhatsApp, and `mark_seen` then `typing_on` on Instagram.
   - `send_button_message` is interactive reply buttons on WhatsApp, and a button template on Instagram, with a media header sent first as its own attachment (see ADR draft 0023 in `docs/backlog/in_progress/261106-architecture-hardening/adr-drafts/`).
   - `send_list_message` is a list on WhatsApp, and quick replies on Instagram.
   - `send_carousel` is an interactive media carousel on WhatsApp, and a generic template on Instagram.
   - `send_location` / `send_contact` are native on WhatsApp, and text (name, address and maps link / contact card) on Instagram; `send_sticker` is an image on Instagram.
2. **Inbound uses the same shapes.** A User's choice arrives as an `InboundMessageWebhook` with interactive selection evidence (`get_interactive_selection()`), whether it came from a WhatsApp button or list reply, an Instagram quick reply or an Instagram postback. No Platform gets its own lane for an event another Platform already models.
3. **Lossy adaptation is explicit, never silent.** An adapter may drop presentation that its Platform cannot show: for example, Instagram has no list row descriptions and no footers, so footers fold into the text. It must never drop meaning. When a call cannot be honoured (too many options, missing required media, a limit exceeded), it raises a clear error before any provider call. Adapters document each mapping in their method docstrings and in `docs/public-contract.md`.
4. **Exceptions are capabilities, not contract methods.** An action that only some Platforms have, with no reasonable mapping elsewhere (Instagram comments, comment moderation, post reads), lives behind a focused capability reached with `IMessenger.capability()`. Event families that only one Platform emits (comments, mentions, message edits) keep their own Universal Webhook types, because there is nothing to unify them with. Platform-native escape hatches stay private to the adapter.
5. **Typed contracts, never raw dicts.** A Universal Webhook exposes Platform content through typed models (the same message models inbound messages use), not a serialized provider payload. A shape with no model yet is named (`native_type`) and left `None` rather than passed through as a dict.
   Three bounded exceptions, decided 2026-11-05:
   - `raw_webhook_data` on every lane is diagnostic evidence, excluded from serialization and read only through `get_raw_webhook_data()`. Host logic must not depend on it.
   - `CustomWebhook.raw_value` is the input of a parser the Host registered itself for a field Wappa does not model (`register_webhook_field`); the typed contract is `parsed`.
   - `CallWebhook.session` / `raw_call` stay untyped until WhatsApp Calling is integrated (backlog: `docs/backlog/drafts/` Calling PRD).

   Unmodelled Meta input is tolerated and reported (`META_SCHEMA_DRIFT`), never exposed to Hosts, and an unknown change field maps to `SystemWebhook(UNSUPPORTED_EVENT)` on both Platforms ([ADR-0010](0010-payload-routed-whatsapp-webhook.md), amended 2026-11-05).
   `send_contact` takes the typed, Platform-neutral `ContactCard` (`wappa.domain.contacts`), not a dict.
6. **Separate responsibilities get separate contracts (SRP).** `IMessenger` only sends conversation messages and acknowledges them. Storing and fetching media, Templates, comments and account connection are different responsibilities, so each has its own interface, even when several Platforms implement it.

## Contract map

| Layer | Contract | WhatsApp | Instagram |
| --- | --- | --- | --- |
| Core (every Platform, adapted) | `IMessenger`: `send_text`, `send_image` / `send_video` / `send_audio` / `send_document`, `send_sticker`, `send_button_message`, `send_list_message`, `send_cta_message`, `send_carousel`, `send_location`, `send_contact`, `mark_as_read` | native | adapted (see rule 1) |
| Core, WhatsApp-only today | `send_location_request`, `send_contact_request` | native | raises `UnsupportedOperationError`: a text prompt would not return the location or phone, so the meaning cannot be kept. Telegram has native equivalents. Hosts gate on `supported_operations`. |
| Shared capability | `IMediaLibrary`: `upload(path, family, *, mime_type=None) → media_id`, `download(media_id, *, max_bytes=None)` (keywords added 2026-11, architecture hardening H-18) | Media API | `message_attachments` (reusable) + CDN reader |
| Platform capability | `ITemplateMessaging`: text / media / location Templates | yes | — |
| Platform capability | `ICommentControls`, `IConversationContentReader` | — | yes |
| Inbound (one shape) | `InboundMessageWebhook` (text, media, selections), `StatusWebhook`, `SystemWebhook`, `CustomWebhook` | yes | yes |
| Inbound (one shape) | `OutboundEchoWebhook` (`process_outbound_echo`): a message the business sent, echoed, typed content | Coexistence `smb_message_echoes` (`BUSINESS_APP`) | `message_echoes`, Wappa's own sends filtered out by `ISentMessageRegistry` (ADR-0018) |
| Inbound (one shape) | Reactions: `InboundMessageWebhook` with a `BaseReactionMessage` (`target_message_id`, `emoji`, `is_removal`) | `reaction` | `message_reactions` |
| Inbound (one shape) | `MessageUpdateWebhook` (`process_message_update`): edits and deletions, typed replacement | `edit` / `revoke` | `message_edit` / unsend |
| Inbound (one shape) | `EntryReferral` (`entry_referral`): what brought the User here (ad, post, link) | Click-to-WhatsApp `referral` | ad / ig.me `referral` |
| Backfill (one shape) | `HistoryThread` of `HistoryMessage`: pushed as `HistorySyncWebhook` (`process_history_sync`), pulled through `IConversationHistoryReader` | push (Coexistence `history`) | pull (Conversations API) |
| Inbound (one shape) | `InboxConnectionWebhook` (`process_inbox_connection`): an Inbox stopped or resumed | `account_offboarded` / `account_reconnected` | deauthorize callback (`/webhook/inboxes/instagram/deauthorize`) |
| Inbound, one Platform emits | `CallWebhook`, `ErrorWebhook`, `SystemWebhook` contact sync / group / user action (WhatsApp); `IncomingCommentWebhook`, `MentionWebhook` (Instagram) | | |

Hosts check `messenger.supported_operations` or `capability()`, never the Platform name.

### Resolved violations (2026-11-05)

Six places broke rules 2 and 5 and are fixed:

1. **Edits and deletions** had two lanes (WhatsApp `InboundMessageWebhook(EDIT/REVOKE)`, Instagram `MessageUpdateWebhook`). Both now use `MessageUpdateWebhook`, with the typed replacement in `message`.
2. **Inbound reactions** existed only on WhatsApp; Instagram dropped them. Both are now `InboundMessageWebhook` with a `BaseReactionMessage`.
3. **Referrals** had two models (`AdReferralBase`, `EntryReferral`). They are one concept, entry-point attribution ("what brought this User here"): an ad on either Platform, a WhatsApp post, an Instagram ig.me link. `EntryReferral` (with `EntryPointKind`) is the one model on both; `ad_referral` is deprecated and still filled for WhatsApp for one release.
4. **History backfill** was a raw WhatsApp dict with no Instagram counterpart. It is now one typed shape: pushed (`HistorySyncWebhook`) where the Platform pushes, read (`IConversationHistoryReader`) where it only allows reads.
5. **Raw payloads** (`coexistence_payload`, `group_update`, `user_action`, `EntryReferral.raw`) are typed models (`ContactSync`, `GroupUpdate`, `UserAction`, `EntryReferral`). `platform_event` remains only on `UNSUPPORTED_EVENT`, as evidence of an event that has no contract yet.
6. **Connection lost** was a WhatsApp `SystemWebhook` and a Host-only Instagram route. Both now produce `InboxConnectionWebhook`.

### Known gaps (recorded, not yet built)

- **`send_reaction(message_id, emoji, target)` is a missing core method.** WhatsApp, Instagram and Telegram all support reactions, so it belongs on `IMessenger`. Today no Platform can send one; inbound reactions already share one shape (`BaseReactionMessage`). Backlog: `docs/backlog/drafts/261105-mid-send-reaction-core-method.md`.
- **Account connection is its own contract.** Connecting an Inbox (Meta Business Login for WhatsApp Embedded Signup and Instagram, a bot token for Telegram) happens before a Messenger exists, so it is an Inbox Connector, not an `IMessenger` capability. Decided in [ADR-0017](0017-inbox-connector-contract.md) and implemented in `wappa.connections`.

## Consequences

- Host code, Scores and Agents use one vocabulary on every Platform. A conversation built for Instagram runs on WhatsApp, and the reverse, except for the capability-gated exceptions.
- Adding a Platform means writing adapter mappings and tests against the existing contract. Adding a contract method needs a new ADR-level reason: an action that no existing method can express.
- Some fidelity is lost on purpose (Instagram list descriptions, WhatsApp postback-versus-quick-reply distinctions). The lost presentation is documented per mapping.
- The unreleased `InteractionWebhook`/`process_interaction` lane, `mark_seen`, `set_typing`, `send_quick_replies`, `send_buttons`, `send_card`, `IMessenger.download_media` and `IMessenger.reply_comment` are removed before release. `reply_comment` moves to `ICommentControls.reply_comment`, and media reads and uploads move to `IMediaLibrary`.
- **Breaking (released API):** `send_text_template`, `send_media_template` and `send_location_template` leave `IMessenger` for `ITemplateMessaging`. Middleware keeps the same method names, so window guards and caches keep working; direct callers migrate (see `CHANGELOG.md`).
