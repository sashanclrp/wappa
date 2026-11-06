# Adding a Platform (Telegram, Teams, …)

## Contents

- Definition of done
- Order of work
- Emulation rules
- What a Host must learn

## Definition of done

A Host's existing handler, written against `self.messenger`, answers on the new Platform with no edit. The only shared-code changes are the composition root and the vocabulary. `tests/test_third_platform_contract.py` is the executable spec: it registers a fake Platform keyed by the reserved `PlatformType.TELEGRAM` from adapters alone, drives a signed callback through dispatch to a `send_text` reply, and has a guard test that fails on any new Platform branch in shared modules. A real Platform passes the same shape with real adapters.

## Order of work

Each step depends on the one before; don't parallelize them.

1. **Research and decide.** Read the Platform's send, webhook, media and auth docs and its rate limits into the PRD's references (stamped `checked_on`). Run `grill-with-docs` for its names (Inbox ID, Platform Account, User ID) and record the decisions in the ADR clusters (ADR-0022 identity, ADR-0023 inbound, ADR-0025 Messenger, ADR-0026 connection, ADR-0028 WhatsApp first).
2. **Vocabulary.** A `PlatformType` member (`wappa/schemas/core/types.py`; Telegram is already reserved) and an active/inactive credential record pair plus its `RECORD_TYPES` entry (`wappa/domain/inbox/credentials.py`). `InboxRef.cache_namespace` already qualifies by Platform.
3. **Inbound adapter.** `wappa/webhooks/<platform>/` (pure models), `wappa/processors/<platform>_processor.py` (pure lane translation, no I/O), routing that resolves every entry's Inbox before returning deliveries, and a `PlatformWebhooks` implementation (`platform`, `builtin_fields`, `route`, `translate`). A non-Meta Platform adds `authenticate` and its own callback authenticator (ADR-0023): authenticate bytes before parsing.
4. **Outbound adapter.** `wappa/messaging/<platform>/`: an `IMessenger` over the Platform's client, its `supported_operations`, its `_capabilities` (checked by `tests/test_capability_map.py`), an `IMediaLibrary`, a media-rules module refusing unfit files before I/O, and, when it has Platform-only features, a Platform Messenger (`PlatformEntry.build_platform_messenger`) with its typed `WappaEventHandler` attribute.
5. **Connection.** An `IInboxConnector` in `wappa/connections/<platform>.py` when accounts connect through a login flow.
6. **Composition root.** One `PlatformEntry` in `build_platforms` and its fields in `BUILTIN_FIELDS` (`wappa/platforms.py`). Nothing else in shared code. The guard test proves it.
7. **Tests.** Mirror the Instagram suite: the processor against recorded payloads (`scripts/promote_payload.py` turns live captures into fixtures), `tests/test_one_method_per_action.py`, `tests/test_messenger_parity.py` and `tests/test_messenger_parameter_reach.py` with the new adapter added, the media rules, and the third-Platform contract with the real adapter.
8. **Live gates.** A live test plan like the Instagram PRD's: text round trip, every media family by link and upload, every interactive form, statuses, connection. Results go in the PRD before rules change (`live-verification.md`).
9. **Docs and skills.** `ARCHITECTURE.md` "Multi-Platform Strategy", the context docs, `docs/public-contract.md`, `CHANGELOG.md`, and the Host skills (`shipped-skills.md`).

## Emulation rules

- Neutral shapes and limits follow WhatsApp (ADR-0028). Never relax a WhatsApp limit to fit the new Platform. Shared limits become the strictest across installed Platforms, which is a Host-visible break: list it.
- Emulate what the Platform lacks (Instagram turns captions into follow-up text, lists into quick replies, location into a Maps link), and raise `UnsupportedOperationError` only when emulation would lie to the User.
- A call that becomes several messages returns one `MessageResult`: `success` only when every part was accepted, the final part's `message_id` (the media's for media plus caption), `platform_response["wappa_parts"] = {"message_ids": [...], "delivered": n}` (`PARTS_KEY`, built by `_Parts` in `wappa/messaging/instagram/messenger.py`; reuse it), and an error naming how many parts were delivered.
- Media: enforce the Platform's accepted formats and size caps before I/O; never convert.
- Rate limits go through the shared governor pattern (`wappa/messaging/meta/graph.py` for Meta; a non-Meta transport needs its own) and surface as `rate_limited` with `retry_after`.

## What a Host must learn

Add `wappa/cli/skills/wappa-apps/references/<platform>.md` (what it adds to a message, its Platform-only features), a column in `media-formats.md` (and keep the unified kit valid for every Platform, or add a rendition row), a row in `connecting-accounts.md` and `meta-app-setup.md` or a new setup file, the new hook rows in the `wappa-apps` lane table, and evals that send the same handler to the new Platform.
