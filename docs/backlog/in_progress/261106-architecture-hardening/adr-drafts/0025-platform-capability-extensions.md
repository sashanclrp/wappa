# One mechanism for Platform capabilities, including profile reading

Status: Proposed, 2026-11-05. Draft for H-17, H-22, H-23, H-24, H-25, H-26.

## Context

ADR-0016 rule 4 puts Platform-only actions behind focused capabilities reached with `IMessenger.capability()`, and ADR-0021 decision 4 gates HTTP routes on those capabilities. The code mixes this with a second mechanism: `whatsapp_only(inbox_ref, ...)` runs only inside routes that happen to build a `WhatsAppClient`, so static WhatsApp routes answer 200 under `/api/instagram`, and Templates are gated on the Platform name because `InboxTemplateTransport` hardcodes `InboxRef.whatsapp` through a private `_messenger`. ADR-0021 says Templates have no capability interface although `ITemplateMessaging` exists and is public. Flows have no contract in either direction. Wappa also has no way to read a User's profile: Instagram DM Users arrive with only an IGSID, and Hosts cannot call Graph without the Inbox token. WhatsApp Cloud API has no User lookup at all.

## Decision

1. A Platform-only capability is a focused, action-named interface in `wappa/domain/interfaces/`, returned from the adapter's `capability(kind)` mapping, reached by Hosts with `require_capability(kind)` and by routes with `requires_capability(kind)` (501 when absent). This is the only extension mechanism. Platform-only inbound families are Universal Webhook classes emitted only by their adapter.
2. Capability map: WhatsApp has `ITemplateMessaging`, later `IFlowMessaging` and `ICallControls`; Instagram has `ICommentControls`, `IConversationContentReader`, `IConversationHistoryReader` and `IUserProfileReader`. Private replies remain a `send_text` target (ADR-0014, ADR-0021 rule 6).
3. `whatsapp_only` exists in one place: the router-level dependency of the WhatsApp extension router, which mounts the WhatsApp operations that have no capability (limits, validators, Template info, Media API info and delete, `/health`). Shared routes live in a neutrally named messaging router.
4. Templates: `OutboundRuntime` moves to `wappa/messaging/outbound_runtime.py`; `OutboundRuntime.templates(inbox_ref)` builds the transport over the public `messenger(inbox_ref)`; `send()` checks `capability(ITemplateMessaging)` before any I/O and returns `REJECTED` with `capability_unsupported` when absent, never `INDETERMINATE`.
5. ProfileReading is the `IUserProfileReader` Platform capability: `get_user_profile(user_id) -> ReadResult[UserProfile]` with `UserProfile(user_id, display_name, username, picture_url)`. It is one of the five core interfaces of the target shape, shipped as a capability because only Instagram has a real lookup; WhatsApp's supply is the webhook `UserBase.profile_name`. It is promoted to a Shared capability when a second Platform implements a real lookup. It is never called from intake or dispatch; caching is Host policy. The Inbox's own business profile is a separate capability (`IInboxProfileReader`), built later.
6. Flows: inbound `nfm_reply` becomes a typed `FlowReply`. When `IFlowMessaging` lands (the second sending capability), `SendInvocation` carries its owning capability kind and the pipeline drops `TEMPLATE_METHODS`; not before.

## Consequences

Adding a WhatsApp or Instagram capability is one interface, one adapter and one mapping entry, with no shared-code branch. Breaking: `OutboundRuntime.templates` signature, `InboxTemplateTransport` constructor, route-family module names and OpenAPI tags, `/api/instagram/*/limits` and validators now 501, `/health` slimmed. This deliberately deviates from "every Platform implements ProfileReading" because a mandatory interface would have one real adapter and one pass-through.

## Supersedes

None fully. Amends ADR-0021 decision 4 (Templates are a capability; the WhatsApp extension router is the one name-gated surface), ADR-0016 contract map (adds `IUserProfileReader`, Flows and Calls rows) and ADR-0006 wording (transport keyed by `InboxRef`). Banner all three on acceptance.
