---
checked_on: 2026-11-08
checked_against: Wappa CHANGELOG.md (0.34.3) and docs/migration/v0.34.0-from-0.33.md, v0.34.1-from-0.34.0.md
revision: 5
---

# Upgrading a Host to a new Wappa version

## Contents

- Method
- 0.34.2 → 0.34.3 checklist
- 0.34.1 → 0.34.2 checklist
- 0.34.0 → 0.34.1 checklist
- 0.33 → 0.34 checklist
- After the upgrade

## Method

Wappa releases are clean cuts: a renamed or removed API has no alias, and every break is listed under its version in `CHANGELOG.md`. Don't search for shims; apply each break.

1. Pin the target version and read its whole `CHANGELOG.md` section, plus `docs/migration/v<new>-from-<old>.md` when present (both ship in Wappa's source; read them from the repository or the installed sdist).
2. Turn every "Breaking" line into a checklist item and grep the Host for each old name.
3. Fix the code, then run the Host's tests with `SYSTEM_STRICT_META_SCHEMA=1` so payload drift fails loudly.
4. Run data migrations (cache namespaces, below) with old workers stopped, then deploy.
5. Refresh this skill set: `wappa init` never overwrites an existing skill, so copy the new version's `wappa/cli/skills/` over the old folders (or delete them and re-run `wappa init` in a scratch folder and copy).

Upgrade one minor version at a time when several are pending.

## 0.34.2 → 0.34.3 checklist

Rename `WP_WEBHOOK_VERIFY_TOKEN` to `META_WEBHOOK_VERIFY_TOKEN`, `WP_ACCESS_TOKEN` to `META_WHATSAPP_ACCESS_TOKEN`, `WP_PHONE_ID` to `META_WHATSAPP_PHONE_NUMBER_ID`, `WP_BID` to `META_WHATSAPP_BUSINESS_ACCOUNT_ID`, and `WAPPA_STRICT_META_SCHEMA` to `SYSTEM_STRICT_META_SCHEMA`. Remove every retired key, including empty ones: settings initialization fails even when the replacement is present. Explicit routing still rejects the three deployment-wide WhatsApp credentials.

Wappa removes `settings.openai_api_key` and `platform_configs.openai` from detailed health. Move provider configuration to the Host's `LLM_PROVIDER_OPENAI_API_KEY`, pass it explicitly to the provider client, and remove `OPENAI_API_KEY` from the environment. Host plugin examples use `CRM_API_TOKEN` and `CRM_WEBHOOK_SECRET`. There is no data migration. See `docs/migration/v0.34.3-from-0.34.2.md`.

## 0.34.1 → 0.34.2 checklist

No signature or data migration is required. Pin 0.34.2 and re-run timer tests with unavailable and inactive Inbox credentials: non-sending Scheduled Event handlers now run, and a send raises the original typed Directory error on first use. Failed resolution is not cached; the next use retries. Delivery logs omit raw Delivery Addresses while results retain them. Cache overrides still require the Host to supply a qualified namespace; validation of raw overrides was deferred.

## 0.34.0 → 0.34.1 checklist

This patch breaks one signature; see `docs/migration/v0.34.1-from-0.34.0.md`.

1. **Resolver.** `IIdentityResolver.resolve(recipient, *, inbox_ref)` replaces `inbox_id`. Key the lookup on the whole `InboxRef` and drop any prefix stripping or Platform guessing. Update fakes too.
2. **Direct constructions.** `HandlerStateService` and `TemplateStateService` require `inbox_ref=`, and `resolve_event_user_id` takes `inbox_ref=`.
3. **Reconnect.** `process_inbox_connection` can now run with `self.messenger` set to `None` on `account_reconnected`. Guard handlers on that lane.
4. **Scripts.** `wappa migrate cache-namespaces` exits 1 while conflicts remain. `--json` gives the full report.

## 0.33 → 0.34 checklist

0. **Cache keys.** WhatsApp namespaces become `whatsapp__<pnid>`. With 0.33 stopped: `wappa migrate cache-namespaces -i <pnid> --redis-url "$REDIS_URL"` (dry run), then add `--apply` (`--json-root` for JSON). Pub/Sub subscribers move to `wappa:notify:whatsapp__<pnid>:*`.
1. **Targets.** Every send takes `target=DirectMessage(inbox_ref=..., addresses=...)`. `recipient=` is gone. Build replies from `webhook.user.delivery_addresses()` and stored addresses with `DeliveryAddresses.of(...)`.
2. **Templates.** `self.whatsapp.templates.send_text_template(...)` (and media and location). `OutboundRuntime.templates(inbox_ref)` takes an `InboxRef`. `override=True` became `routing_policy="cloud_messages_fallback"`.
3. **Media.** Use `self.messenger.media` (`upload`, `download`, `info`, `delete`). `IMediaHandler` and `IAttachmentMediaReader` are removed. Media rules now raise `ValueError` before any call (WhatsApp voice notes OGG/Opus, stickers WebP 512×512, and others).
4. **Event lanes.** Edits and revokes go to `process_message_update`, business echoes to `process_outbound_echo`, history to `process_history_sync`, and offboard and reconnect to `process_inbox_connection`; those `SystemWebhook` types are removed. Exhaustive `match` statements over `UniversalWebhook` need the six new members.
5. **Webhook payloads.** `coexistence_payload`, `ad_referral` and `AdReferralBase` are removed: use `entry_referral` and `is_from_ad()`. `InboundMessageWebhook.whatsapp` is removed: read `webhook.user`.
6. **Results.** `MessageResult` moved to `wappa.domain.results` (also `wappa.messaging`), and `platform` is required. There is no `.failed` or `.outcome`: use `result.success` or `result.aggregate_outcome` (including partial acceptance). Historical `message_outcome(result)` remains available.
7. **Custom Messengers and fakes.** New signatures: `mark_as_read(message_id, target, *, typing=False)`, `send_contact(contacts, target)`, `send_cta_message(header=InteractiveHeader | None)`, `send_audio(..., is_voice=)`. New methods: `send_carousel` and the abstract `resolve_platform_user_profile`. The adapter classes are now `WhatsAppMessengerAdapter` / `InstagramMessengerAdapter`; `WhatsAppMessenger` / `InstagramMessenger` are the Platform Messengers on the handler.
8. **Interactive values.** Use the neutral `InteractiveHeader` (`HeaderType` is removed). Limits are the strictest across Platforms and fail when the value is built.
9. **HTTP.** `create_whatsapp_router` became `create_messaging_router`. Host routes using `get_inbox_execution_context` must declare `{platform}`. Failed sends answer 4xx (they answered 200). WhatsApp-only routes answer 501 under `/api/instagram`. API sends now run Messenger middleware.
10. **`InboxRef` everywhere.** `create_context(inbox_ref, user_id, *, include_messenger)`, `add_cron(..., inbox_ref=)`, `build_channel` / `build_pattern(inbox_ref)`, and `sse_event_scope(platform=)` (now required).
11. **Renames.** `mount_whatsapp_callback` became `mount_webhook_callback`, and `WHATSAPP_WEBHOOK_CONTRACT_DRIFT` became `META_SCHEMA_DRIFT`. `register_webhook_field` requires `platform=`. Unknown WhatsApp fields reach `SystemWebhook(UNSUPPORTED_EVENT)` instead of answering 400.
12. **Your own middleware.** Wappa now falls back from phone to BSUID by itself (131030, 131062). Remove any Host BSUID-fallback middleware, which would fight it.

## After the upgrade

Run one live round trip per Platform and Inbox type, check a status webhook arrives, and check `scripts/redis_inspect.py` (from a Wappa checkout) shows keys under the new namespace. Then read the "Known gaps" line in `wappa-apps` again: a gap closed in the new version is now a supported API.

## Moving from 0.34.5 to 0.34.6

Rename the explicit MetaApplicationConfig constructor parameter and attribute to `webhook_verify_token`; `META_WEBHOOK_VERIFY_TOKEN` stays unchanged. There is no alias. Adopt the shared universal JSON keys: Instagram text `content`, selections `selected_option_id`/`selected_option_title`, media `media_id`/`caption`/`media_family`, context `original_message_id`; WhatsApp Template quick replies use the selection keys too. Native dictionaries are behind `message.get_platform_data()` for text/selection/media/reaction. Unavailable facts are nullable, including evidenced inbound `mime_type`; resolved downloads expose `MediaBytes.content_type`.

Use Inbox-qualified `UserIdentity` from `user.identity(inbox_ref)`, `profile.identity(inbox_ref)` and `result.identity()`, and the SSE envelope's additive identity. Instagram phone fields are now empty, Parent BSUID parsing works, and WhatsApp excludes proven digit echoes before I/O. Shared HTTP addresses remain opaque until selected adapter validation. Use `result.parts` and `result.aggregate_outcome` to avoid whole-call retries after partial acceptance; both serialize. `error_evidence` retains native code/subcode and neutral category; temporary is separate from retry safety. `messenger.discovery` and shared local capabilities/message/media limit routes describe adapter support without Platform branches. Full removed-key and constructor mapping: repository `docs/migration/0.34.6.md`.

The 0.34.6 addendum adds typed MessagePart.content for actual per-part structure (persist only accepted parts), plus Redis expiry due indexing/recovery. Keep Host idempotent fences; recovered events retain the existing hook/source and add metadata.recovered, original scheduled_for and generation execution_id. Old armed keys lack due entries and must be re-armed for recovery. Cancellation/rebind update pending metadata too, without changing trigger key names. See the scheduled-tasks skill's expiry reference.
