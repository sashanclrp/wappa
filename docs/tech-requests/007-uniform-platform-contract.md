# Wappa v0.34.6 request

## Context

Read-only audit of Wappa v0.34.5, commit `0e8c727` (clean checkout), against Symphonai’s `wappa-v0341` worktree. ADR-0025 promises one contract per shared action. The remaining gaps concern shared representations, validation and discovery.

Evidence paths below are relative to the Wappa repository; Host paths are relative to `backend/symphonai/`.

## Request

1. **Make identity factories symmetrical. — Low**
   
   **Current:** `InboxRef.whatsapp(...)` and `PlatformAccountRef.whatsapp(...)` exist without Instagram counterparts ([identity.py:75](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/domain/inbox/identity.py:75), [identity.py:146](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/domain/inbox/identity.py:146)). **Uniform contract:** document the generic constructors as canonical for every Platform; if Platform shortcuts remain supported, provide matching Instagram factories. **Compatibility:** additive; existing constructors need no change.

2. **Remove WhatsApp recipient validation from shared HTTP request models. — High**
   
   **Current:** shared `DeliveryRequest` uses `RecipientIdentifier` for both `recipient` and `addresses`; its validator accepts only WhatsApp phones/BSUIDs and applies their normalization. Instagram IDs pass only when their shape happens to satisfy those rules. `mark-as-read`, meanwhile, accepts an opaque string ([recipient.py:134](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/schemas/core/recipient.py:134), [recipient.py:199](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/schemas/core/recipient.py:199), [basic_models.py:28](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/schemas/requests/basic_models.py:28)). **Uniform contract:** shared request models preserve nonblank opaque addresses; the selected Platform adapter validates and normalizes them consistently with Python `DirectMessage` sends. **Compatibility:** retain request keys and WhatsApp normalization at its adapter boundary; document the validation-stage change.

3. **Use Platform-aware identity evidence throughout SSE/API dispatch. — High**
   
   **Current:** public `classify_meta_identifier` treats every non-BSUID string as a phone and misses Parent BSUIDs. Outgoing API dispatch and SSE publishing call it without consulting `event.platform`, so an Instagram IGSID becomes `phone_number`. Inbound processing correctly leaves Instagram phone/BSUID fields empty ([context.py:135](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/core/sse/context.py:135), [api_event_dispatcher.py:88](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/core/events/api_event_dispatcher.py:88), [handlers.py:122](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/core/sse/handlers.py:122)).
   
   **Uniform contract:** use one Inbox-qualified identity projection containing the recommended User ID, delivery addresses and optional evidence across webhook Users, profiles, results and SSE. Preserve opaque Instagram IDs; classify WhatsApp evidence through one parser covering regular and Parent BSUIDs. `UserBase.user_id` and `delivery_addresses()` already provide the core accessors; expose equivalent information consistently rather than introducing another canonical-ID policy. **Compatibility:** preserve envelope keys; correcting falsely populated phone fields is a documented behavior fix. Durable identity reconciliation remains Host-owned.

4. **Apply delivery-address sanitation before sending, not only to returned results. — High**
   
   **Current:** `MessageResult` removes a phone that is demonstrably a BSUID digit echo, but `UserBase.delivery_addresses()` includes the raw phone, and WhatsApp delivery orders phone-looking values first without the same exclusion ([results.py:89](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/domain/results.py:89), [identity.py:130](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/core/webhook_interfaces/base_components/identity.py:130), [delivery.py:65](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/messaging/whatsapp/messenger/delivery.py:65), [recipient.py:153](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/schemas/core/recipient.py:153)).
   
   **Uniform contract:** every adapter owns address normalization, exclusion and ordering before I/O. Apply the existing corroborated digit-echo rule to WhatsApp delivery candidates, including Parent evidence when available; Hosts pass known evidence without reproducing transport rules. **Compatibility:** keep `DeliveryAddresses`; preserve raw provider evidence separately. Document that proven echoes cease being attempted.

5. **Make universal message/context serialization actually uniform. — High**
   
   **Current:** WhatsApp text serializes `content`; Instagram serializes `text`. WhatsApp selections expose `selected_option_id/title`; Instagram exposes `selection`/`text`. WhatsApp media exposes `media_id`, `caption` and media metadata; Instagram’s universal projection exposes `url`, `text` and `attachment_type`. Instagram context serializes `reply_to_message_id`, while WhatsApp context serializes `original_message_id`. Built-in incoming SSE publishes these dictionaries directly ([WhatsApp text:225](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/whatsapp/message_types/text.py:225), [Instagram text:37](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/instagram/message_types/text.py:37), [Instagram selection:65](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/instagram/message_types/selection.py:65), [Instagram attachment:58](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/instagram/message_types/_attachment.py:58), [handlers.py:70](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/core/sse/handlers.py:70)).
   
   **Uniform contract:** one typed serialized projection per message family, with common text, selection, media-reference and reply-context keys; unavailable facts remain nullable. Keep native payloads behind the native-evidence accessor. **Compatibility:** changing existing keys is a wire break; publish a migration under Wappa’s clean-cut policy (`docs/public-contract.md:5`).

6. **Represent unknown inbound MIME types honestly. — Medium**
   
   **Current:** the universal media interface promises a MIME type, but Instagram supplies nominal JPEG, AAC and PDF constants without webhook MIME evidence. WhatsApp reads actual supplied MIME evidence. A Host must know which Platform’s value is trustworthy ([media.py:30](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/core/base_message/media.py:30), [Instagram image:18](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/instagram/message_types/image.py:18), [Instagram audio:18](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/instagram/message_types/audio.py:18), [Instagram file:18](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/instagram/message_types/file.py:18)).
   
   **Uniform contract:** separate media family from nullable, evidenced MIME type; use downloaded `MediaBytes.content_type` when resolved. **Compatibility:** an additive nullable MIME field avoids immediately changing `media_type`; replacing its semantics requires a migration.

7. **Expose consistent error evidence and neutral classification. — High**
   
   **Current:** Instagram send results preserve Graph `code/subcode`; WhatsApp’s exception mapping uses `MetaGraphError.code`, which strips the subcode, and additionally replaces `131062` with a symbolic tag. Universal webhook errors instead require integer codes and their helpers classify HTTP-like numeric ranges ([graph.py:108](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/messaging/meta/graph.py:108), [WhatsApp errors:114](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/messaging/whatsapp/errors.py:114), [Instagram delivery:126](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/messaging/instagram/messenger/delivery.py:126), [webhook errors:25](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/webhooks/core/webhook_interfaces/base_components/errors.py:25)).
   
   **Uniform contract:** retain provider code/subcode separately from a Wappa category, with shared classifications for authentication, permission, messaging window, address rejection, rate limit and unknown outcome. Apply them to synchronous results and webhook error evidence; retry safety must remain separate from “temporary.” **Compatibility:** add structured evidence/classification fields while preserving existing codes; normalize historical codes only through a documented break.

8. **Make aggregate send outcomes safe without inspecting provider-evidence dictionaries. — High**
   
   **Current:** `wappa_parts` is already shared, but `message_outcome()` only checks `success`, `retry_after` and `INDETERMINATE`. Instagram aggregation retains the last failure after earlier accepted parts, so the helper can report `rate_limited` or `rejected` for a partially accepted call. The necessary part evidence disappears from normal JSON serialization ([results.py:114](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/domain/results.py:114), [Instagram delivery:82](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/messaging/instagram/messenger/delivery.py:82), [public-contract.md:92](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/docs/public-contract.md:92)).
   
   **Uniform contract:** expose typed, serializable normalized parts and an aggregate classification that distinguishes partial acceptance from a refusal with nothing accepted, while retaining the failed part’s outcome and retry delay. Use it for single-message WhatsApp sends too. **Compatibility:** additive fields/helper can coexist with historical `message_outcome`; changing that helper’s enum requires migration.

9. **Complete operation-level capability and limit discovery. — Medium**
   
   **Current:** both adapters advertise `mark_as_read`, without separately declaring typing support or receipt scope. `messenger.media` exists on both, but Instagram `info/delete` raise; message/media limits have WhatsApp-only HTTP paths. Hosts cannot discover these details through the same supported contract ([WhatsApp operations:57](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/messaging/whatsapp/messenger/adapter.py:57), [Instagram operations:89](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/messaging/instagram/messenger/adapter.py:89), [media_library.py:18](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/domain/interfaces/media_library.py:18), [limits.py:25](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/api/routes/whatsapp/limits.py:25)).
   
   **Uniform contract:** extend discovery with media suboperations, typing/read scope, target kinds, and accepted media formats/sizes; expose message/media limits under `/api/{platform}`. Keep existing button/media operation names and `send_text:private_reply`. Platform-only extras retain their typed Platform Messengers. **Compatibility:** additive discovery; preserve existing WhatsApp routes.

10. **Rename shared Meta configuration in the Python contract. — Low**
    
    **Current:** the environment uses `META_WEBHOOK_VERIFY_TOKEN`, but explicit `MetaApplicationConfig` requires `whatsapp_webhook_verify_token`, which the shared controller reads for Instagram verification too ([meta_application.py:31](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/core/config/meta_application.py:31), [meta_application.py:40](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/core/config/meta_application.py:40), [webhook_controller.py:76](/home/sashanclrp/personalProjects/mimeia/products/wappa/wappa/wappa/api/controllers/webhook_controller.py:76)).
    
    **Uniform contract:** `MetaApplicationConfig.webhook_verify_token`; use Meta-wide terminology in associated diagnostics. **Compatibility:** constructor-field rename requires a migration under the no-alias policy; the environment variable stays unchanged.

## Why

These changes let Hosts consume one representation and let adapters own provider translation. The highest-value fixes prevent fabricated phone identities, invalid address attempts, misleading media metadata and unsafe whole-message retries after partial acceptance.

## Host-side branches Symphonai can delete once these land

- The Platform split in [services/wappa/recipient_scope.py:30](/home/sashanclrp/personalProjects/mimeia/products/symphonai-worktrees/wappa-v0341/backend/symphonai/services/wappa/recipient_scope.py:30), replacing manual phone/BSUID scope construction with uniform identity evidence.
- The Parent-BSUID classifier repair in [core/meta_identity.py:43](/home/sashanclrp/personalProjects/mimeia/products/symphonai-worktrees/wappa-v0341/backend/symphonai/core/meta_identity.py:43).
- WhatsApp transport sanitation in [services/wappa/targets.py:40](/home/sashanclrp/personalProjects/mimeia/products/symphonai-worktrees/wappa-v0341/backend/symphonai/services/wappa/targets.py:40); retain Host-known alias enrichment and same-subject checks.
- Ordinary text/media/selection routing through the Instagram-specific processor at [engine/pipeline/processors/base.py:213](/home/sashanclrp/personalProjects/mimeia/products/symphonai-worktrees/wappa-v0341/backend/symphonai/engine/pipeline/processors/base.py:213), after adopting the uniform projection; retain story/share-specific behavior.
- Duplicate multipart classification at [core/messenger/delivery_outcome.py:110](/home/sashanclrp/personalProjects/mimeia/products/symphonai-worktrees/wappa-v0341/backend/symphonai/core/messenger/delivery_outcome.py:110); retain Host admission and history policies.

## Excluded differences and already-uniform surfaces

- **Canonical User ID:** `UserBase.user_id` already selects native ID, then BSUID, then phone; historical merges and durable identity promotion remain Host responsibilities.
- **Profiles:** both adapters return `PlatformUserProfile`; Instagram lookup failures return outcomes, while wrong-Platform evidence raises `ValueError` on both (`messenger/profile.py` in each adapter).
- **Replies:** both send adapters accept `reply_to_message_id`; Instagram’s precise quote-rejection fallback is already adapter-owned and recorded.
- **Receipts:** outbound WhatsApp per-message read versus Instagram thread-level seen is a real difference; inbound Instagram currently requires `read.mid` and emits message-addressed `StatusWebhook(READ)`. No watermark-only contract was evidenced (`instagram/models/messaging.py:32`, `instagram/processor/messages.py:63`).
- **Namespaces:** Inbox and Platform Account cache namespaces are already Platform-qualified; no encoding change is needed.
- **Platform-only features:** Templates, Flows, billing, groups and Coexistence versus Instagram comments, private replies, stories and history access need distinct capabilities.
- **Media formats:** codec/size restrictions and Host transcoding are real provider differences; discovery should describe them, not promise conversion.
- **Legacy configuration/CLI:** WhatsApp single-Inbox credentials and `migrate cache-namespaces --whatsapp-inbox` describe genuinely WhatsApp-specific legacy data.

Implementation rules:
- One way to say one thing on every Platform; adapters own provider translation; Hosts never branch on Platform for shared actions.
- Item 1: make the generic constructors canonical AND add InboxRef.instagram(account_id) and PlatformAccountRef.instagram(...) so every Platform has the same shape; document the rule in public-contract.md.
- Items 5 and 10 are wire/API breaks: Wappa's public contract has a clean-cut, no-alias policy (docs/public-contract.md near the top). Implement them as clean cuts and write a migration guide docs/migration/0.34.6.md listing every renamed/removed key, field and constructor parameter with before/after, plus anything Hosts must change for items 2,3,4,7,8.
- Additive items (6,7,8,9) add typed fields/helpers without breaking existing ones unless the item says otherwise.
- Update docs/public-contract.md, the affected ARCHITECTURE.md files, CHANGELOG.md under an Unreleased/0.34.6 entry (do not change the version number), and the Host skills.
- Tests: add focused tests per item (both Platforms where shared) and run the full suite: `uv run --frozen pytest -q` (if uv cannot resolve offline, use the existing .venv: `.venv/bin/python -m pytest -q`). Also ruff check/format as CODING_STANDARDS requires. All must pass; report counts honestly.

Final answer: per item, what changed (files) and its compatibility note; the migration-guide summary; test counts; anything not done and why.

## Addendum

11. **Structured per-part evidence (extends item 8). — High**
Current: `wappa_parts.parts[]` reports each emulated/split part's role, exact `text`, `message_id` and `outcome`, but not the structured content a part carried (buttons, quick replies, carousel elements, media reference). A Host that must store only what the customer received (e.g. an Instagram CTA where the media header was accepted but the buttons part was refused) can reduce the text but cannot tell which structure arrived, so its history still claims buttons were sent. Uniform contract: each part also carries a typed, serializable `content` describing exactly what that part sent (e.g. `{"buttons": [...]}`, `{"quick_replies": [...]}`, `{"elements": [...]}`, `{"media": {"type", "id"|"url"}}`), `null` for plain text; the same on WhatsApp's single native part. Additive.

12. **Restart-safe expiry triggers. — High**
Current: Wappa's expiry runtime (RedisExpiry / expiry dispatcher, Redis keyspace notifications over Pub/Sub) loses any trigger whose key expires while no process is listening (restart, deploy, crash). Observed live: an Agent trigger armed 15 s before a dev reload was never delivered; the Host had to add its own sweep for that one action, while every other action (message_sync, conversation_window, template_rollback, human_takeover, scheduled timers) can still be lost. Uniform contract: when a trigger is armed, Wappa also records it in a durable due-time index (e.g. a Redis sorted set per Inbox namespace scored by due time, with the action and identifier); a fired delivery removes it; on startup and on a short periodic tick Wappa dispatches every overdue entry whose key is gone, at least once, through the same handler path with a flag/context indicating a recovered (late) delivery. Handlers already rely on idempotent fences. Document the at-least-once guarantee in public-contract.md and the expiry ARCHITECTURE; provide a migration note (existing armed keys created before upgrade have no index entry). Bounded work per tick, no KEYS scans.

Final answer additions: per new item, files changed, compatibility note, tests.
