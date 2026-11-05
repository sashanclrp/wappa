# Instagram integration research

Scope update (2026-11-03): the [PRD](scope.md) records the completed grilling
session's selections. The inventories below are research/history, not current
exclusions or claims of implemented support. In particular Live comments,
public mentions, comment-control primitives, supported media bytes retrieval,
trusted credential reuse and extension webhook intake are selected. Publishing,
content/account analytics and moderation policy remain consumer-owned.


Test record: [simple text tests and learnings](../tests/simple-text-test.md).


Implementation update (2026-11-03): initial Instagram text/seen/echo-system lanes,
explicit Instagram credential records, DirectMessage sends, and the sibling echo
example are implemented locally. CLI GET verification and signed offline echo
have been tested. A real Instagram text exchange, outbound echo event, and READ
status were verified at 11:24 America/Bogota on 2026-11-03. Self-service OAuth
onboarding and Symphonai integration remain pending.
See [setup.md](setup.md#local-implementation-ready-for-callback-verification) and
[ADR-0014](../../../../adr/0014-instagram-text-and-explicit-messenger-targets.md).
Capability inventories below retain the research-stage snapshot; they are not
an assertion that every originally missing foundation remains unimplemented.

Date: 2026-11-03. Provider facts, current-code findings, capability gaps, and research uncertainties. IG = Instagram; WA = WhatsApp. No live Meta account tests have been performed.

Setup walkthrough: [setup.md](setup.md), documenting Unified Login dashboard configuration and pending verification.

Related documents: [decisions and scope](decisions.md), [proposed roadmap and verification](design-roadmap.md).

## 1. Research scope

Compare Instagram with WhatsApp and Wappa's current inbound/outbound interfaces. Proposed API mappings in inventory tables are analysis, not implemented contracts or scope approval.

Making text work proves one complete path; it does not establish support for every message type or webhook.

## 2. Functional areas: more than Messages and Posts

These are research groupings, not newly established bounded contexts. Wappa's existing context map remains authoritative. Instagram's product surface does not need to map one-to-one to Wappa folders or interfaces.

| Functional area | Includes | Relationship to Wappa |
| --- | --- | --- |
| Messages | DMs, attachments, interactive selections, seen notifications, message edits/removals, private replies triggered by comments, outbound echoes. | Core inbound and outbound runtime work. |
| Posts and comments | Post/media reads, public comments and replies, parent-comment relationships, mentions, comment moderation, publishing. | Content reads and public replies support conversations. Publishing and moderation are additional capabilities, not automatically in scope. |
| Insights | Media/account insights, story insights, engagement measurements. | Separate read/analytics capability if selected; should not be disguised as incoming messages. Business analytics and durable reporting belong to the host. |
| Account and conversation control | Account/profile metadata, handover, standby, opt-ins, policy notifications, inbox control. | Typed system/control events where relevant. No invented User for an account-only event. |

Authentication, onboarding, permissions, subscriptions, credential rotation, and HTTP lifecycle cut across these areas. They are infrastructure responsibilities, not another type of message. Advertising is a separate adjacent area: ad accounts, campaigns, creatives, attribution, and paid-delivery decisions do not become Wappa responsibilities simply because Meta supplies the APIs.

Important cross-area flow: a public comment belongs to Posts/comments; a private reply to that comment is delivered through Messages; the recipient's subsequent answer is an ordinary incoming DM. The event and the delivery mechanism do not have to belong to the same functional area.

## 3. Current Wappa baseline

Only WhatsApp has a complete built-in adapter today. `PlatformType` contains `instagram`, `telegram`, and `teams`, but enum values and detection heuristics do not prove implemented Platform support. Facebook Messenger has no enum member today. `MessengerFactory` currently rejects non-WhatsApp Platforms.

| Existing seam | Current role | Instagram implication |
| --- | --- | --- |
| `WappaBuilder` | Startup composition. | Assemble selected Platform adapters and their dependencies. Registration syntax shown in the conversation was illustrative, not an existing API. |
| `BaseWebhookProcessor` / processor factory | Platform payload translation into Universal Models. | Add an Instagram processor and schemas; preserve purity. |
| `InboundRuntime` | Dispatch Context, Messenger, cache, DB, handler binding, dispatch. | Reuse orchestration, extending event admission/binding where comments or control events require it. |
| `route_whatsapp_payload` | WhatsApp batch splitting, Inbox resolution, account membership checks. | Instagram needs its own routing rules; a WhatsApp `changes` parser is not a generic Meta router. |
| `MetaCallbackAuthenticator` | Authenticate exact body bytes before parsing/resolution. | Shared Meta trust mechanism; a signature header does not identify which Meta Platform sent the event. |
| `MessengerFactory` | Resolve credentials and construct the Inbox-bound Messenger. | Add Instagram construction and lifecycle wiring. |
| `IMessenger` / `WhatsAppMessenger` | Public outbound seam and WA implementation. | Replace WA assumptions in shared types and introduce explicit capabilities. |
| `MessengerPipeline` / `SendInvocation` | Middleware, lifecycle emission, outbound invocation capture. | `recipient: str` assumptions must migrate with targets, results, and events. |
| Inbox Directory and credential records | Wappa-owned credential authority in explicit mode. | Add Instagram record variants and onboarding mapping; do not reuse a WA record with misleading values. |
| `IMediaHandler` | Upload/info/download/delete and validation. | Audit carefully: current contract closely follows WA's media-ID lifecycle. Instagram post media is a different resource. |

Composition direction is recorded in [decisions.md](decisions.md).

### 3.1 Shared contracts that still assume WhatsApp

- `UserBase.user_id` derives from BSUID or phone number. It has no proper general native sender-ID field for Instagram. Never store an Instagram-scoped ID in `phone_number` or label it a WA BSUID.
- `InboxBase` requires `display_address` and `platform_account_id`. Instagram admission must define honest values and optionality rather than fabricate a phone number or a WABA-like account relationship.
- `IIdentityResolver.resolve(recipient, *, inbox_id)` accepts an unqualified Inbox ID today. A future cross-Platform lookup needs an Inbox Reference, consistent with the glossary; this is a migration item, not an already-complete seam.
- `MessageResult` lives under the WA package, defaults to WA, and types raw evidence as `WhatsAppAPIResponse`. Shared results must represent Instagram evidence without pretending it is a WA response.
- Interactive interface arguments import WA models, including buttons, headers, and list sections.
- `IMessenger` requires WA Template operations. Instagram Interactive Messages (called templates in some Meta wire formats) are distinct from WhatsApp Templates.
- `PlatformDetector.detect_from_headers` currently treats `X-Hub-Signature-256` as WA evidence. That is not sufficient once multiple Meta Platforms are accepted. Detection must follow authenticated payload/route evidence.

These are concrete limits on the current claim that another Platform can be added without changing any public contract.

## 4. Identity and references

| Concept | WhatsApp | Instagram | Facebook Messenger, later |
| --- | --- | --- | --- |
| Receiving Inbox ID | Meta `phone_number_id`. | Receiving professional account ID. | Receiving Page ID. |
| Sender's native identity | BSUID when present, otherwise sender phone number under current Wappa policy. | Instagram-scoped sender ID. | Page-scoped user ID, PSID. |
| Inbox Reference | `InboxRef(whatsapp, inbox_id)`. | `InboxRef(instagram, inbox_id)`. | Would require a new Platform member. |
| Outbound private address | Valid WA Delivery Address, e.g. BSUID or phone. | Eligible Instagram-scoped recipient ID. | Eligible PSID. |
| Comment-triggered private target | No equivalent in WA messaging. | Comment ID qualified by Inbox Reference. | Research separately. |

WA `phone_number_id` identifies the receiving business Inbox; it is not the sender's phone number. Native sender IDs must retain their Inbox/Platform scope. Do not equate identities across accounts or assume a public comment author ID is automatically an eligible ordinary DM destination. The private-reply API addresses the comment.

Candidate Comment/Post references and schemas are recorded in [decisions.md](decisions.md).

## 5. Inbound webhook inventory and normalization

### 5.1 Universal families

| Family | WA | IG | Existing Wappa contract | Proposed treatment |
| --- | --- | --- | --- | --- |
| Incoming private message | Yes. | Yes. | `InboundMessageWebhook`; WA implemented. | Same contract for selected message variants. |
| Status | Sent/delivered/read/failed and supported variants. | Seen notifications; no assumed parity with WA statuses. | `StatusWebhook`. | Preserve evidence; never manufacture delivery events from send acceptance. |
| System/control | Identity, preferences, account, groups, synchronization. | Handover, opt-in, policy/control. | `SystemWebhook`. | Typed subtype details; not a bag for every unknown payload. |
| Public comment | No WA Cloud API equivalent. | Comments and Live comments. | None. | New `IncomingCommentWebhook` and handler hook. |
| Call | WhatsApp Calling. | No equivalent established in this messaging API. | `CallWebhook`. | Keep optional Platform capability. |
| Provider error notification | Supported WA payloads. | Only where actual notification evidence exists. | `ErrorWebhook`. | API error responses remain outbound errors, not synthetic inbound callbacks. |
| Registered provider extension | Custom WA fields. | Needs Instagram-specific implementation. | `CustomWebhook` and field registry for WA. | Explicit typed extensions for selected non-core events. |

Current host hooks: `process_message`, `process_status`, `process_error`, `process_system_webhook`, and `process_call`. `process_comment` does not exist. `process_api_message`, `process_external_event`, and `process_cron_event` also exist, but are not new Instagram webhook families.

### 5.2 Message-content comparison

| Content/action | WA today | Instagram capability | Mapping / constraint |
| --- | --- | --- | --- |
| Text | Parsed. | Supported. | Shared text shape. |
| Image, audio, video | Parsed. | Supported attachments. | Shared media variants; native IDs/URLs and restrictions differ. |
| Document/file | Parsed. | File attachments; outbound guide documents PDF. | Shared document concept; do not copy WA MIME guarantees to IG. |
| Sticker | Parsed. | Incoming image/sticker representations; outbound heart sticker. | Preserve subtype; arbitrary WA sticker upload is not equivalent to IG heart. |
| Button / quick-reply selection | Parsed `button` and `interactive` types. | Quick replies and postbacks. | Shared selection semantics, with Platform-specific constraints. |
| Reaction / unreact | Incoming WA reaction schema exists. | Reaction notifications. | Existing WA behavior; no IG implementation. |
| Message edit | WA lifecycle schema exists. | `message_edit`. | Reference original message; not a new independent text message. |
| Message removal | WA revoke schema exists. | `is_deleted` in message notification. | Preserve deletion semantics and affected reference. |
| Location / contact card / order | WA schemas exist. | No matching WA-style structured contracts established here. | Keep WA-specific capabilities. |
| Shared Instagram post/Reel/story | No corresponding IG native content contract. | Shared-content attachments. | New typed content/reference variant if selected. |
| Story reply / messaging story mention | No equivalent IG story context. | Messaging attachment/reply context. | A message with story context, distinct from a public mention event. |
| Business-originated echo | WA Coexistence echo built in. | Echo notifications. | Outbound direction; never run as a new incoming User message. |

Evidence: [IG notification examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples), [IG changelog](https://developers.facebook.com/docs/instagram-platform/changelog), and [WA webhook reference index](https://developers.facebook.com/documentation/business-messaging/whatsapp/llms.txt).

### 5.3 Instagram native webhook fields

This is an inventory of the reviewed field matrix plus the documented edit event, not a promise that every field is available under every login configuration. The selected authorization setup must have its own verified subscription manifest. Meta's messaging overview and field matrix use some differing names, including reaction/referral spellings; do not implement guessed aliases from prose.

| Native event/field | Meaning | Proposed Wappa handling | Implemented for IG? |
| --- | --- | --- | --- |
| `messages` | DMs, attachments, quick-reply selections, story context. | `InboundMessageWebhook` for User-authored content. | No. |
| `messaging_postbacks` | Button/ice-breaker/menu selection. | Interactive message variant. | No. |
| `message_reactions` | React or unreact to a message. | Reaction variant only if later selected. | No. |
| `message_edit` | User edits a message. | Lifecycle/edit variant. | No. |
| Deletion inside `messages` | `is_deleted` notification. | Lifecycle/removal variant. | No. |
| `messaging_seen` | Recipient saw an outbound message. | `StatusWebhook`. | No. |
| `comments` | Public comment activity. | New comment family for relevant actions. | No. |
| `live_comments` | Comment on a live broadcast. | Comment family with Live context and different reply deadline. | No. |
| `mentions` | Public mention in media/comment; setup-specific delivery. | Typed mention event if selected. | No. |
| `message_echoes`, or echo inside `messages` | Message sent by the professional account. | Typed outbound echo/system event. | No. |
| `messaging_referral` | Entry-point/referral context. | Message context if associated; typed event if standalone. | No. |
| `messaging_optins` | Messaging opt-in action. | Typed system event. | No. |
| `messaging_handover`, `standby` | Conversation control/routing. | Typed system/control event. | No. |
| `message.admin_text` / `message.handoff_reason` | Meta Business Agent handoff notice for eligible apps; may lack an ordinary message ID/text. | System/control event; do not fabricate a User text message. | No. |
| `messaging_policy_enforcement` | Policy notification, setup-dependent. | Typed system event. | No. |
| `response_feedback` | Feedback notification, setup-dependent. | Typed extension initially. | No. |
| `story_insights` | Story analytics, setup-dependent. | Analytics capability/extension. | No. |

Sources: [field and permission matrix](https://developers.facebook.com/documentation/instagram-platform/webhooks/fields), [examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples), [edit-event changelog](https://developers.facebook.com/docs/instagram-platform/changelog). Under Instagram Login, mentions may be included in `comments`; under other configurations, `mentions` is a separate field. Subscription names are not necessarily event-object names.

### 5.4 WhatsApp native handling in this checkout

| Native field/payload | Current mapping |
| --- | --- |
| `messages` with User messages | `InboundMessageWebhook`. |
| `messages` with statuses | `StatusWebhook`. |
| `messages` with errors | `ErrorWebhook`. |
| System message within `messages` | `SystemWebhook`, e.g. number change. |
| `user_id_update` | User identity change system event. |
| `user_preferences` | Marketing preference system event. |
| `user_actions` within `messages` | Typed User-action system event; payload may have no User identity. |
| `business_username_updates` | Business username system event. |
| `group_participants_update` | Group participant system event. |
| `calls` | `CallWebhook`. |
| `account_offboarded`, `account_reconnected` | Account-scoped system events. |
| `history`, `smb_message_echoes`, `smb_app_state_sync` | History/echo/app-state synchronization system variants. |
| Registered custom fields | `CustomWebhook` with host-registered Pydantic parser and handler. |

Additional WA management fields documented by Meta include account alerts/review/update, business capability updates, template status/quality/components/category updates, phone-number name/quality updates, security, payment configuration, partner solutions, and automatic events. Do not confuse API availability with built-in Wappa support: the registry permits explicit typed integrations but does not implement each management payload natively.

`SystemWebhook` is a shared envelope, not proof that an IG handover and a WA BSUID change have the same fields. Full current Platform subscription catalogs exceed the messaging scope of this draft; [Meta's WA documentation index](https://developers.facebook.com/documentation/business-messaging/whatsapp/llms.txt) is the source for further selection.

## 6. Outbound interface inventory

### 6.1 Every current IMessenger operation

The interface has 17 operations, plus `platform` and `inbox_id` properties. Every operation with a `recipient` parameter participates in the proposed `target=` migration. `mark_as_read` has a message-ID contract and needs a separate design review.

| Current operation | WA implementation | Instagram capability/equivalence | Target/design implication |
| --- | --- | --- | --- |
| `send_text` | Yes. | Text/link message. | DirectMessage; PrivateReply text when eligible. |
| `send_image` | Yes. | Image messages. | DirectMessage initially; sources/captions need validation. |
| `send_video` | Yes. | Video attachments. | DirectMessage initially; native limits differ. |
| `send_audio` | Yes. | Audio attachments. | DirectMessage initially. |
| `send_document` | Yes. | PDF documented by IG send guide. | DirectMessage; cannot promise every WA document MIME type. |
| `send_sticker` | Uploaded sticker. | Heart sticker. | Same method name would need honest variant semantics. |
| `send_button_message` | WA reply buttons. | Quick replies and postback buttons. | DirectMessage; current WA header/footer/button shapes are not portable unchanged. |
| `send_list_message` | WA list picker. | No native WA-style list equivalent established. | DirectMessage on WA only. No silent carousel/text substitution. |
| `send_cta_message` | WA URL CTA. | URL button in button/generic template. | DirectMessage with shared intent and native restrictions. |
| `send_contact_request` | WA contact-information request. | No equivalent established. | WA-only capability. |
| `send_text_template` | Approved WA Template. | IG Interactive Messages have different semantics; Meta calls some wire formats templates. | WA DirectMessage; do not homologate solely by the word template. |
| `send_media_template` | Approved WA Template with media header. | No equivalent approved Template contract. | WA DirectMessage. |
| `send_location_template` | Approved WA Template with location header. | No equivalent. | WA DirectMessage. |
| `send_contact` | Structured contact card. | No equivalent established. | WA DirectMessage. |
| `send_location` | Structured coordinates/location. | No equivalent established. | WA DirectMessage. |
| `send_location_request` | Request native location sharing. | No equivalent established. | WA DirectMessage. |
| `mark_as_read` | Marks a specific message; `typing=True` does not implement the promised typing behavior in the current adapter. | `mark_seen` targets a recipient/conversation. | Separate message-reference and conversation-action semantics. |

There is no public generic `send_media()` today. `WhatsAppMessenger._send_media` is private implementation machinery. A future generic media operation is a separate decision, not required merely to replace recipients with targets.

IG additionally documents multi-image sends, generic-template cards/carousels, quick replies, published-post sharing, reactions, and sender actions. The current shared interface has no dedicated operations for these. [Send Messages](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/), [quick replies](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/quick-replies), [button templates](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/button-template), [generic templates](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/generic-template), [sender actions](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/sender-actions).

Future target rules and public-reply API alternatives are recorded in [decisions.md](decisions.md).

### 6.2 API and media surfaces outside IMessenger

Wappa currently composes WhatsApp HTTP routes under `/api/whatsapp`: text/read actions, media sends, interactive sends, specialized sends, Templates, template information, media upload/info/download/delete, limits/validation, health, and state handlers. Mounting is capability/profile controlled. Existing callback routes are `/webhook/inboxes/{platform}` for GET verification and POST intake; a Platform-shaped URL does not mean the Platform is implemented.

There are no built-in Instagram send, comment-reply, post-content, or moderation HTTP routes today. Adding Python methods does not automatically create their HTTP contracts. Public replies and publishing/moderation are mutations and need explicit route composition consistent with embedded/standalone behavior.

`IMediaHandler` currently exposes `upload_media`, `upload_media_from_bytes`, `upload_media_from_url`, `upload_media_from_stream`, `get_media_info`, `download_media`, `download_media_tempfile`, `get_media_as_bytes`, `stream_media`, `delete_media`, and validation/limit helpers. These are not post reads or public publishing operations. WA media IDs, Instagram message attachments, Instagram posts, and host-stored files are distinct resources even when all contain an image.

## 7. Private replies: verified special behavior

Meta's private-reply guide documents the following flow and restrictions:

1. A User comments on eligible professional-account content.
2. A comment webhook supplies the triggering comment identity.
3. Send to `/{IG_ID}/messages` with `recipient.comment_id`, not an ordinary `recipient.id`.
4. Only one private reply message can be sent for the triggering comment; normal follow-up requires the recipient to respond.
5. Post/Reel private replies have a seven-day deadline from the comment; Live replies must happen during the broadcast.
6. After the recipient responds, follow-up must respect the applicable response window; the private-reply guide specifies 24 hours after that response.

The ordinary messaging guide also documents action-dependent windows, including eligible Click-to-Direct cases. Do not generalize every interaction into a single fixed 24-hour rule, and do not treat a comment as an unrestricted DM grant.

A normal public post by another person does not, by itself, authorize a DM to its author. Public mentions, messaging story mentions, public comment replies, and private replies are separate capabilities. Instagram is not the Facebook Page visitor-post model.

Sources: [private replies](https://developers.facebook.com/documentation/instagram-platform/private-replies), [ordinary messaging](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/), [public comment moderation/reply guide](https://developers.facebook.com/documentation/instagram-platform/comment-moderation). A public reply uses `POST /{IG_COMMENT_ID}/replies`.

## 8. Content retrieval and Symphonai ownership research

Reviewed checkout: `/home/sashanclrp/personalProjects/mimeia/products/symphonai`. Findings describe the backend Meta/ads lanes inspected during this session, not an audit of every external integration or generated skill.

| Existing Symphonai component | What it actually does |
| --- | --- |
| `backend/symphonai/services/meta/marketing_api/client.py` | `get_ad`, `list_ads`, `observe_ads`, account inspection and authorization exchange. `_AD_FIELDS` requests ad/account identity, ad-set/campaign hierarchy, status/schedule/issues. It does not request creative content or Instagram post content. |
| `backend/symphonai/domains/whatsapp/ads/referral.py` | Purely translates webhook-provided headline/body/media URLs into agent context. Organic `source_type="post"` uses a separate post-context path. |
| `backend/symphonai/domains/whatsapp/ads/media_analysis.py` | Downloads a supplied media URL and generates/caches a media description. It is not a post-by-ID API. |
| `backend/symphonai/domains/whatsapp/ads/ad_attribution_service.py` | Persists ad observations/snapshots and attribution. Organic post referrals are excluded from the ad attribution path. |
| `backend/symphonai/services/meta/ARCHITECTURE.md` | Shared HTTP/error mechanics and focused provider clients, with domain orchestration kept outside the client package. |

No Instagram post-by-ID reader was found in those backend lanes. Ads and posts can refer to one another, but an Ad ID, Creative ID, Instagram media ID, and Facebook post ID are not interchangeable. Meta's creative API exposes fields such as `effective_instagram_media_id` and `effective_object_story_id`; mapping an ad to its referenced content is a separate operation from retrieving the content. [Official creative-read example](https://www.postman.com/meta/facebook-marketing-api/request/xowugm6/retrieving-adcreative-details-l-1).

The proposed ownership split and content-reader contract are recorded in [decisions.md](decisions.md).

## 9. Not implemented: capability inventory

This inventory records missing implementations and provider applicability. Edit scope selections in the matching ID rows in [decisions.md](decisions.md#scope-worksheet). No row here implies a commitment to implement.

### 9.1 Instagram adapter and shared-contract foundations

| ID | Missing capability | Applies to | Existing Wappa support / gap description |
| --- | --- | --- | --- |
| F01 | Instagram callback admission and routing | IG | No complete adapter. Authenticate, split batches, identify professional-account Inbox, resolve credentials, validate before scheduling. |
| F02 | Instagram credentials and authorization setup | IG | Directory records/factory construction are WA-only. Need explicit IG record/configuration; no token-type guessing. |
| F03 | Universal native User identity and Delivery Address | Both | Current User model derives identity from WA evidence. Needed to carry IG sender IDs honestly without corrupting WA identity. |
| F04 | Explicit `target=` migration | Both | All recipient-based IMessenger methods use strings today. Pipeline, APIs, examples, events and host integrations must migrate together. |
| F05 | Platform/operation/target capability validation | Both | No complete common outbound capability matrix. Reject invalid combinations and cross-Inbox targets before I/O. |
| F06 | Neutral outbound result/evidence types | Both | Shared result lives under WA and retains a typed WA response. Public comments also need comment-reference results. |
| F07 | Instagram HTTP/API surfaces | IG | No send/comment/content routes. Decide which Python capabilities receive HTTP routes and how mutations are mounted. |
| F08 | Cross-Platform identity resolver scope | Both | Current resolver takes raw `inbox_id`; use qualified identity when lookup can cross Platforms. |

### 9.2 Messages: missing implementations and capabilities

| ID | Missing capability | Applies to | Description and current interface gap |
| --- | --- | --- | --- |
| M01 | IG incoming text and outgoing text | Both; IG implementation missing | WA has the complete path. Add IG parsing, normalization, Messenger sending, and result evidence. |
| M02 | IG image/audio/video/file messages | Both; IG implementation missing | Existing send methods cover the broad families; IG translation, source/limit handling and inbound schemas are absent. PDF is the documented IG outbound file type. |
| M03 | IG seen events and seen action | Both | WA status/read support exists, but IG status evidence and recipient-based `mark_seen` do not fit the existing method unchanged. |
| M04 | Portable buttons/quick replies | Both | WA buttons exist. IG quick replies/postbacks need neutral models and native constraints; no dedicated quick-replies method exists. |
| M05 | IG URL CTA | Both; IG implementation missing | WA `send_cta_message` exists. IG Button Messages require native format translation and validation. |
| M06 | Cards/carousels | IG verified; WA equivalence needs separate research | IG Message Cards/Carousels display images/text/buttons (Meta wire term: generic template). No dedicated common operation or model. |
| M07 | Multi-image send | IG verified; other Platform parity not audited | IG can send a collection of images. Current public interface sends one image per call. |
| M08 | Published-post sharing in a DM | IG | Send an owned published post to an eligible DM recipient. Not the same as downloading and resending an image; no current method. |
| M09 | Story reply/mention and shared-content parsing | IG | Preserve story/post/Reel reference and context. Existing universal message variants do not implement the IG content model. |
| M10 | IG message edits/removals | Both; IG implementation missing | WA inbound lifecycle schemas exist. IG edits/deletions need translation and lifecycle handling. This does not imply outbound edit/delete support. |
| M11 | Outbound reactions/unreact | Both | Provider capability, but no IMessenger operation. Receiving a reaction is not proof that Wappa can send one. |
| M12 | IG incoming reaction normalization | Both; WA already parses inbound reactions | No IG processor. Define ignore/unsupported admission behavior if excluded; do not silently treat it as text. |
| M13 | IG heart sticker | Both have stickers, with different contracts | IG heart action is not WA's arbitrary uploaded sticker. Existing `send_sticker(source, ...)` cannot be reused honestly without a variant decision. |
| M14 | Standalone typing actions | Both | IG supports typing_on/off. Current WA `mark_as_read(typing=True)` does not provide complete typing behavior; no dedicated interface operation. |
| M15 | IG outbound echo handling | Both; WA Coexistence echo exists | Synchronize business-originated messages without dispatching them as User input or starting reply loops. |
| M16 | IG referral/entry-point context | Both have referral concepts | Existing WA referral models are not an implemented IG referral mapping. Preserve standalone versus message-associated events. |
| M17 | Message/conversation history retrieval | IG capability; WA has a distinct Coexistence history event | No shared conversation-read API. Fetching history is separate from accepting history-sync callbacks. |
| M18 | IG User profile read | IG | Query available profile data for a scoped User. No dedicated public IG profile service; not required merely to reply to text. |

### 9.3 Posts and comments

| ID | Missing capability | Applies to | Description and current interface gap |
| --- | --- | --- | --- |
| P01 | Incoming public comment event | IG | Add typed comment, author, Post Reference, parent-comment context and dispatch hook. No `IncomingCommentWebhook` or `process_comment` exists. |
| P02 | Public comment reply | IG | Reply under a particular comment via its native replies endpoint. No IMessenger method or HTTP route; choose dedicated operation or PublicReply target. |
| P03 | Private reply triggered by comment | IG initially | DM addressed through comment evidence. No PrivateReply target; preserve single-reply/deadline restrictions and follow-up rules. |
| P04 | Post-by-ID content retrieval | IG | Fetch authorized caption/media/permalink/child content. Not IMediaHandler.get_media_info and not a webhook side effect. |
| P05 | Comment/reply read and pagination | IG | Fetch comment details or replies beyond the notification. No standalone read service. |
| P06 | Live comment handling | IG | Live context and stricter private-reply deadline. No Live-specific runtime contract. |
| P07 | Public mention/tag handling | IG | Notification/read of public account mentions or tags; distinct from a story mention delivered as a DM. No typed universal event/service. |
| P08 | Hide/unhide/delete comments | IG | Content moderation, not ordinary text sending. No service/HTTP capability. |
| P09 | Enable/disable comments on owned content | IG | Modify comment availability. Separate content-management mutation; no existing contract. |
| P10 | Publish posts/Reels/stories/carousels | IG | Content creation/publishing with its own workflow and restrictions. Existing send_image/send_video deliver messages, not public posts. |
| P11 | Edit/delete published content where supported | IG | Public-content lifecycle, not message lifecycle. Exact supported operations require endpoint-level research; no current contract. |

### 9.4 Control, insights, and adjacent areas

| ID | Missing capability | Applies to | Description and current interface gap |
| --- | --- | --- | --- |
| C01 | IG handover/standby/admin notices | IG | Typed conversation-control events. SystemWebhook exists, but IG parsing/control semantics do not. |
| C02 | IG opt-in notifications | IG | Preserve subscription/consent event evidence. Not an incoming chat message; no typed IG implementation. |
| C03 | IG policy/response-feedback events | IG, setup-dependent | Explicit policy/feedback handling through system or extension events. No native IG implementation. |
| C04 | Ice-breaker/menu configuration | IG | Configure conversation entry UI and process selections. Configuration methods are absent; receiving a postback is only half the capability. |
| C05 | IG subscription/onboarding automation | IG | Configure authorized account subscriptions and credentials. Not implied by callback route support; exact login flow remains open. |
| A01 | Story/account/media insights | IG | Fetch or receive analytics outside the core message handler. No IG insights service or event mapping. |
| A02 | Ad-to-Instagram-content resolution | IG + Meta Ads, outside WA runtime | Resolve creative references to published content. Symphonai's current backend ad reads do not fetch those creative fields. |
| W01 | Native WA management schemas beyond built-ins | WA | Template/account/quality/security management fields can be registered, but no complete built-in schema/handler inventory exists for every field. |
| W02 | Additional WA message-send families outside IMessenger | WA | Receiving order/group/call events does not imply outbound product/order/Flow/group/call-management APIs. Not exhaustively audited here. |

## 10. Additional findings and unresolved verification

### Shared Meta callback versus Platform identity

Dashboard evidence supplied during setup: Instagram exposes its own Configure webhooks section with Callback URL and Verify token fields. The user reports that the use cases can have separate URLs. This supports separate callback configuration; it does not establish that shared URLs are forbidden. The screen also states that receiving webhooks requires a published app. The preceding screen recommends Unified Login and labels Instagram Login legacy; verify the selected login path before implementing onboarding.

A Meta app, an HTTPS callback URL, an object subscription, and a Wappa Platform are distinct concepts. A common callback can receive configured object subscriptions without merging their semantics: Instagram examples use `object: instagram`; Facebook Messenger Page events use `object: page`; WhatsApp uses `object: whatsapp_business_account`. Page subscriptions can also cover non-messaging activity, so `page` alone does not establish that every field is a supported Messenger event. Account-level authorization/subscriptions remain necessary even when the URL is shared.

Using `/webhook/meta` for all three, or a shared Instagram/Messenger endpoint plus a WhatsApp endpoint, is an HTTP composition option, not a new `meta-messenger` Platform. Keep Instagram and Messenger identities/adapters distinct regardless of URL grouping. Authenticate the exact body before parsing the discriminator; then route supported fields through the proper adapter and resolve the qualified Inbox. Current Wappa routes are Platform-based. The selected separate-Platform callback design is recorded in [decisions.md](decisions.md#callback-url-grouping); Instagram support is not implemented yet. Sources: [Messenger Webhooks](https://developers.facebook.com/documentation/business-messaging/messenger-platform/webhooks), [Instagram examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples).

### Interactive scores and intake primitives

The JSON/Redis CLI application examples define consumer-side `ScoreBase`, `ScoreDependencies`, and `ScoreRegistry` under their `app/scores/` directories. These compose `IMessenger`, `ICacheFactory`, and `InboundMessageWebhook` through `can_handle`/`process`; they are example application code, not a native Instagram workflow engine or a public core Score contract.

Instagram quick replies deliver selected text and payload in a message notification; postback buttons deliver a configured payload through a postback event. URL buttons open a web page. These primitives support consumer-orchestrated conversational questionnaires. They do not establish a native multi-field form equivalent to WhatsApp Flows. The reviewed quick-reply guide disables phone/email contact-information quick replies and suggests text entry instead. Sources: [quick replies](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/quick-replies), [button templates](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/button-template).

### Scoped identities

An Instagram-scoped sender ID must be interpreted within its receiving professional account. The runtime identity is `(InboxRef, user_id)`. One person contacting three professional accounts must not share cache/state merely because the host thinks they are the same person. A host may link these identities using its own verified evidence; scoped IDs alone do not provide that link. WA BSUID is portfolio-scoped, whereas IGSID is account-scoped: reuse Wappa's Inbox isolation, not an assertion that the provider scopes are identical. Current UserBase and identity resolver still require the migration documented above.

### Human escalation options

Meta documents a single-app custom inbox and cross-app Handover Protocol. Cross-app control can serve independent automation and support products. The HUMAN_AGENT policy/tag is distinct from assignment; the guide describes a separate seven-day human-agent window. Approval and exact request fields must be verified for the selected setup. The selected approach and host ownership are in [decisions.md](decisions.md).

### Shares and Creator readiness

Preserve the shared URL and every available attachment/reference field supplied by the webhook. Do not invent a complete Post object or assume that an arbitrary shared URL can be resolved by the owned-post reader. Reads may be unavailable because of permissions, deletion, expiry, or inaccessible content. URL-only shares must remain processable.

The user supplied a Creator prerequisite: call Conversations API before receiving webhooks. Treat this as a selected-login-flow verification item, not a confirmed universal rule: the sources inspected in this follow-up did not establish its scope. Include an explicit Creator onboarding smoke test and, where required by the selected setup, a one-time Conversations API bootstrap before declaring readiness. Do not add a Conversations API request to every webhook.

### Current registration constraints

InboxCredentialService and CredentialRecord currently support WhatsApp only. Meta GET callback verification, account authorization/subscription, and POST event intake are separate operations. See [ADR-0011](../../../../adr/0011-encrypted-inbox-directory.md) for the existing source-driven Directory contract. The proposed connection flow is in [roadmap.md](design-roadmap.md).

## 11. Evidence and source index

Repository findings are from the working tree inspected on 2026-11-03, not a tagged release or live Platform certification. Meta documentation was read during the session, including via direct HTTP when the browsing tool returned rate-limit errors. Provider availability, permission sets, and payload schemas must be rechecked for the selected setup during implementation. No Meta account calls or live webhook/send tests were performed.

### Wappa sources

- [Canonical glossary](../../../../../CONTEXT.md), [context map](../../../../../CONTEXT-MAP.md), [architecture](../../../../../ARCHITECTURE.md), [public contract](../../../../public-contract.md).
- [IMessenger](../../../../../wappa/domain/interfaces/messaging_interface.py), [IMediaHandler](../../../../../wappa/domain/interfaces/media_interface.py), [identity resolver](../../../../../wappa/domain/interfaces/identity_resolver.py).
- [MessengerFactory](../../../../../wappa/domain/factories/messenger_factory.py), [Messenger Pipeline](../../../../../wappa/core/messaging/pipeline.py), [WhatsAppMessenger](../../../../../wappa/messaging/whatsapp/messenger/whatsapp_messenger.py), [MessageResult](../../../../../wappa/messaging/whatsapp/models/basic_models.py).
- [Universal webhooks](../../../../../wappa/webhooks/core/webhook_interfaces/universal_webhooks.py), [User/Inbox components](../../../../../wappa/webhooks/core/webhook_interfaces/base_components.py), [WA message schemas](../../../../../wappa/webhooks/whatsapp/message_types), [field registry](../../../../../wappa/core/events/field_registry.py).
- [Handler hooks](../../../../../wappa/core/events/event_handler.py), [processor factory/detection](../../../../../wappa/processors/factory.py), [Inbound Runtime](../../../../../wappa/core/inbound/runtime.py), [WA routing](../../../../../wappa/core/inbound/webhook_routing.py).
- [Credential records](../../../../../wappa/domain/inbox/credentials.py), [credential ports](../../../../../wappa/domain/inbox/ports.py), [callback routes](../../../../../wappa/api/routes/webhooks.py), [WA route composition](../../../../../wappa/api/routes/whatsapp_combined.py).
- [ADR-0001: Inbox identity](../../../../adr/0001-inbox-id-runtime-scope.md), [ADR-0002: runtime/processor boundary](../../../../adr/0002-inbound-runtime-dispatch-context-clean-break.md), [ADR-0010: payload routing](../../../../adr/0010-payload-routed-whatsapp-webhook.md), [ADR-0011: Inbox Directory](../../../../adr/0011-encrypted-inbox-directory.md).

### Primary Meta sources

- [Instagram webhook overview and login setups](https://developers.facebook.com/docs/instagram-platform/webhooks/).
- [Instagram webhook fields and permissions](https://developers.facebook.com/documentation/instagram-platform/webhooks/fields).
- [Instagram notification examples](https://developers.facebook.com/documentation/instagram-platform/webhooks/examples).
- [Instagram send API, content families, restrictions, and limits](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/).
- [Instagram private replies](https://developers.facebook.com/documentation/instagram-platform/private-replies).
- [Instagram comment reads, moderation, and public replies](https://developers.facebook.com/documentation/instagram-platform/comment-moderation).
- [Instagram quick replies](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/quick-replies), [button templates](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/button-template), [generic templates](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/generic-template), [sender actions](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api/sender-actions).
- [Instagram changelog](https://developers.facebook.com/docs/instagram-platform/changelog), [Instagram full documentation index](https://developers.facebook.com/documentation/instagram-platform/llms.txt), [WA full documentation index](https://developers.facebook.com/documentation/business-messaging/whatsapp/llms.txt).
- [Official Meta Instagram Postman collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api), [creative retrieval example](https://www.postman.com/meta/facebook-marketing-api/request/xowugm6/retrieving-adcreative-details-l-1), [Messenger send API comparison](https://www.postman.com/meta/messenger-platform-api/documentation/iyp204x/messenger-platform-api?entity=request-22794852-c54925d1-6422-49cd-a2d2-e275e3f559c4).
- [Meta's sample Instagram app](https://github.com/fbsamples/original-coast-clothing-ig): useful structure/reference only; older sample policies and login requirements are not authorities over current documentation.

Additional primary sources: [Messenger overview and scoped IDs](https://developers.facebook.com/docs/messenger-platform/overview), [Instagram webhook setup](https://developers.facebook.com/documentation/instagram-platform/webhooks).
