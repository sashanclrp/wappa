# Profile reading (core interface 4) - design only

Status reviewed 2026-11-06: historical pre-hardening audit. Findings and file:line references below describe the audited baseline. Use the [plan status table](../plan.md#code-reality-2026-11-06) for implemented and remaining work; do not rebuild a resolved finding from this snapshot.


## Summary

Verified against the code: Wappa has no way to read a User's profile. The only profile data is what the inbound webhook carries. WhatsApp fills `UserBase.profile_name`, `username` and `country_code` from `contacts[].profile`. Instagram direct-message webhooks carry no name, so an Instagram User arrives as `UserBase(platform_user_id=...)` only. The backlog draft `IProfileReader` is about the Inbox's own business profile, not a User's. It is a real two-adapter seam, but it is a different concern, and its name collides with "ProfileReading". The verifier agrees with the auditor's main recommendation: do not make ProfileReading a mandatory core interface that every Platform implements. WhatsApp Cloud API has no User-profile read, so a WhatsApp adapter would only repeat the webhook name back. Ship one narrow Platform capability, `IUserProfileReader`, reached through `messenger.capability()`. Only Instagram implements it, and it gets promoted to a Shared capability when a second Platform implements it. Three auditor findings (04-4, 04-5, 04-6) are design guidance with no defect behind them. They are folded into the interface proposal and not kept as findings. One auditor finding (04-2) was re-scoped: the draft is not a hypothetical seam, because WhatsApp and Instagram both have a business-profile endpoint.

## Confirmed findings

### 04-1 Gap: no way to read a User's profile; Instagram Users arrive nameless

- Files: `wappa/processors/instagram_processor.py`, `wappa/webhooks/core/webhook_interfaces/base_components.py`, `wappa/webhooks/whatsapp/webhook_container.py`, `wappa/messaging/instagram/messenger.py`, `wappa/messaging/instagram/history.py`
- Principle: missing-interface
- Severity: medium
- Breaking: no. Public surfaces: `wappa.messaging` exports, `IMessenger.capability`, `docs/public-contract.md`, ADR-0025 contract map.
- Evidence: `UserBase` has `username` and `country_code` (`base_components.py:84-91`) and `profile_name` (`base_components.py:94`). `get_display_name()` falls back from profile name to username to user id (`base_components.py:154-160`). WhatsApp fills these from `contacts[].profile` (`webhook_container.py:402-403`, `427-433`). The Instagram messaging path builds `UserBase(platform_user_id=user_id)` and nothing else (`instagram_processor.py:209`). So on Instagram, `get_display_name()` always returns the raw IGSID. The Instagram history reader also returns `UserBase(platform_user_id=user_id)` (`history.py:156`). The Instagram capability map (`messenger.py:222-228`) has comment controls, content, attachments, media library and history, but nothing that reads a User. The one place an Instagram username does arrive is comment authors (`instagram_processor.py:474-478`, `webhooks/instagram/models.py:256-260`), which do not cover direct messages.
- Deletion test: without a Wappa reader, every Instagram Host writes its own Graph `GET /{igsid}` call. Each one needs the Inbox's token, and the credential-authority rule says Hosts never receive Resolved Inbox Credentials. The work cannot be done correctly anywhere except inside the adapter, so the module earns its place.
- Proposed fix: add the `IUserProfileReader` capability (see Interface proposal). Put the adapter in `wappa/messaging/instagram/profile.py` on the shared `InstagramGraph` client, using the same request and failure classification as `history.py:123-136`. Register it in `messenger.py:222-228` beside `IConversationHistoryReader`.
- ADR conflict: none. It fits ADR-0025 rule 4 (an action only some Platforms have is a capability) and the explicit-read rule of ADR-0025.

### 04-3 ProfileReading is a Platform capability, not a mandatory core interface

- Files: `wappa/domain/interfaces/messaging_interface.py`, `docs/adr/0025-messenger-contract.md`, `wappa/webhooks/whatsapp/base_models.py`
- Principle: over-engineering
- Severity: medium
- Breaking: no. Public surfaces: ADR-0025 contract map, `docs/public-contract.md`.
- Evidence: on WhatsApp, a User's name exists only inside inbound webhooks: `ContactProfile` (`base_models.py:49`), which Meta may leave out (`base_models.py:129-132`), and a blank name becomes `None` (`docs/public-contract.md:294`). Nothing in the repo reads a WhatsApp User by id, and Cloud API has no endpoint for it. ADR-0025 already separates a Shared capability with two real adapters (`IMediaLibrary`, `0016...md:34`) from a Platform capability with one adapter (`ITemplateMessaging`, `ICommentControls`, `IConversationContentReader`, `0016...md:35-36`). It says Hosts gate on `capability()`, never the Platform name (`0016...md:46`). `capability()` returns `None` and `require_capability()` raises `UnsupportedOperationError` (`messaging_interface.py:51-65`), so a Platform without the capability needs no stub. The contract map and its Known gaps list (`0016...md:59-62`) have no profile-reading row, so the decision is not recorded anywhere.
- Deletion test: a WhatsApp `IUserProfileReader` could only return the name the webhook already put on `UserBase.profile_name`. Deleting it removes no complexity and moves none to callers, so it is a pass-through. A required core interface with one real adapter is a hypothetical seam.
- Proposed fix: record `IUserProfileReader` in the ADR-0025 contract map as a Platform capability (WhatsApp "—", Instagram "yes"). Do not register it in the WhatsApp Messenger. Move it to the Shared capability row only when a second Platform with a real User lookup implements it. In the target shape, "core interface 4" becomes this capability, not a required `IMessenger` seam.
- ADR conflict: none. It applies ADR-0025 rule 4 as written. It does differ from the target shape's "every Platform implements" wording, and the ADR edit should record that choice explicitly.

### 04-2 Backlog draft `IProfileReader` names the Inbox profile as "profile reader" and adds an untyped `extras` escape hatch

- Files: `docs/backlog/drafts/261105-low-profile-reader-capability.md`, `docs/backlog/BACKLOG-EXECUTION-PLAN.md`
- Principle: stale-doc
- Severity: low
- Breaking: no. Public surfaces: backlog docs only.
- Evidence: the draft's title and proposal (lines 6-16) describe `get_profile() -> ReadResult[InboxProfile]`, which returns the connected Inbox's own business profile. It adds a Platform-specific `extras` mapping for things like WhatsApp quality rating (line 16). The execution plan lists it as `IProfileReader` (`BACKLOG-EXECUTION-PLAN.md:25`). Unlike the auditor's claim, this is not a hypothetical seam: WhatsApp (`/{phone_number_id}/whatsapp_business_profile`) and Instagram (`/{ig_id}?fields=...`) both have a source (draft lines 10-14), so it would have two real adapters. The real problems are two. First, the name `IProfileReader` collides with the User-profile capability this area defines. Second, `extras` is an untyped dict that brings Platform branching back into Host code, which works against the one-shape goal the draft itself states. The Telegram row is harmless, because ADR-0025 uses Telegram as a reference in the same way.
- Deletion test: not applicable. This is a draft; no code exists yet.
- Proposed fix: rename the draft to `IInboxProfileReader` (or similar) so the subject is the Inbox. Drop `extras`. Platform-only fields such as quality rating belong in typed optional fields or in a Platform capability. Keep the draft at low priority and separate from `IUserProfileReader`. Do not fold it into the Inbox Connector. A Connector runs before a Messenger exists (ADR-0025 line 62, ADR-0026), and later re-reads such as quality or name status need a Messenger-bound read.
- ADR conflict: none.

## Rejected findings

- 04-4 "Reuse ReadResult/capability pattern; do not invent a parallel result type or fold into IConversationHistoryReader": this is design guidance, not a defect. It is folded into the Interface proposal. The side remark that `ReadResult` lives in the comment-oriented `conversation_capabilities.py` is true: it is imported by `history_reader.py:15` and also by `media_library.py:21`, which the auditor did not mention. Moving it would only change where the type lives, with no behavior change. That is cosmetic and outside this area.
- 04-5 "Profile reads must be explicit and never auto-invoked by dispatch": nothing violates this today. Existing readers already say "never called by processors or dispatch" (`conversation_capabilities.py:139`), and the history guidance points handlers to `messenger.capability()` (`event_handler.py:401-406`). The rule is kept as a constraint in the Interface proposal.
- 04-6 "Optional exposure as HTTP route is premature": there is no route, so there is nothing to fix. The cited ADR-0024 line 22 is about capability groups applying to every Platform and does not support calling a route premature. ADR-0024 rule 4 (line 16) actually makes a gated read route cheap and consistent. Whether to add the route is noted in the Interface proposal.

## Checked and legitimate

- `wappa/webhooks/core/webhook_interfaces/base_components.py:84-94`: `UserBase.username`, `country_code` and `profile_name` on the Platform-neutral webhook User are the right carrier for what a webhook supplies. No interface is needed.
- `wappa/webhooks/whatsapp/webhook_container.py:400-433`: WhatsApp display-name, username and country-code accessors live inside the WhatsApp adapter. This is legitimate Platform-specific parsing.
- `wappa/messaging/instagram/messenger.py:222-228`: the Instagram capability map is the composition root for Platform capability registration. It is the right home for the new reader, with no branch in shared code.
- `wappa/domain/interfaces/messaging_interface.py:51-65`: `capability()` and `require_capability()` already return `None` or raise `UnsupportedOperationError`, so a Platform without the capability needs no stub.
- `wappa/processors/instagram_processor.py:474-478`: comment authors carry an Instagram `username` from the webhook into `CommentAuthor`, inside the Instagram processor. This is legitimate and is not a profile read.
- `CONTEXT.md:147`: the User Cache is "per-user profile/metadata cache within an Inbox". Caching fetched profiles stays a Host decision on that existing primitive.

## Interface proposal

Module: `wappa/domain/interfaces/user_profile_reader.py`. This is a Platform capability (ADR-0025 contract map), not an `IMessenger` method and not required of every Platform. Following ADR-0025, it has one method for one action.

```python
class UserProfile(BaseModel):
    """A User's public profile as the Platform returns it. Absent fields were not returned or authorized."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    user_id: str                 # Inbox-scoped native id (IGSID on Instagram)
    display_name: str | None = None
    username: str | None = None
    picture_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

class IUserProfileReader(ABC):
    """Read one User's profile for this Inbox. Explicit, Host-invoked; never called by processors or dispatch."""
    @abstractmethod
    async def get_user_profile(self, user_id: str) -> ReadResult[UserProfile]: ...
```

Changes from the auditor's proposal. The neutral model keeps only the four fields any Platform with a User lookup can fill. The Instagram relationship and audience fields (`follower_count`, `is_verified_user`, `is_user_follow_business`, `is_business_follow_user`) are left out until a Host asks for them. Adding them later is a non-breaking addition of optional fields, while putting Instagram-only fields in a neutral model now would have to be undone when the capability is promoted. `raw` (excluded from serialization) follows the existing `PostContent` and `CommentContent` convention (`conversation_capabilities.py:84`, `98`). The method takes `user_id` and no `InboxRef`, because the Messenger is already bound to its Inbox and credentials (`messaging_interface.py:54-57`). It mirrors `IConversationHistoryReader.read_history(user_id, ...)` (`history_reader.py:29-35`). Outcomes reuse the existing `ReadResult` from `conversation_capabilities.py:24-43`: `NOT_FOUND`, `ACCESS_DENIED`, `REJECTED`, `UNAVAILABLE`. Do not create a parallel result type, and do not fold profile reads into `IConversationHistoryReader`, because they change for different reasons.

Adapters: Instagram gets `wappa/messaging/instagram/profile.py`, which calls `GET /{igsid}?fields=name,username,profile_pic` through `InstagramGraph`, uses the same failure classification as `history.py`, and is registered in `messenger.py:222-228`. WhatsApp has no adapter: its supply is `UserBase.profile_name` and `username` from the webhook, and `capability(IUserProfileReader)` returns `None`. Promote the capability to the ADR-0025 Shared capability row only when a second Platform implements a real lookup.

Constraints: profile reads are never made during inbound intake or dispatch. Enriching `UserBase` in `instagram_processor.py:209` would add network I/O and rate-limit failures to webhook handling. Caching stays Host policy on the User Cache, and Wappa adds no profile TTL cache. An HTTP route is optional. If one is added, it goes in the existing `conversation_reads_router` as `GET /conversations/{user_id}/profile` with `requires_capability(IUserProfileReader)`, following `conversations.py:237-246` and ADR-0024 rule 4, so other Platforms answer 501 with no extra code.

Out of scope: the Inbox's own business profile (backlog draft, see 04-2) is a separate, two-adapter Shared capability, to be renamed `IInboxProfileReader` and built later.
