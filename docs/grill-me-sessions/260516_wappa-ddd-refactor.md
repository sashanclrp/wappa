Grilling Session — All Questions + Recommendations

Here's everything I need resolved before writing docs and executing. I'm grouping by theme:

---
1. owner_id — The Ghost in the Machine

Your PRD says "keep owner_id as optional host metadata," but the codebase has an OwnerMiddleware that extracts owner_id from the URL path at position 3:
/webhook/messenger/{owner_id}/{platform}. That middleware conflicts with your proposed route shape /webhook/inboxes/{inbox_id}/{provider} — there's no owner_id URL segment in your new routes.

Questions:

- 1a. Does the OwnerMiddleware get deleted entirely, or does owner_id survive as a header/query param/app-level config?
My rec: Delete OwnerMiddleware. If Symphonai needs to pass an owner context, it does so via a request header (X-Owner-Id) or app-level settings — not URL structure. Wappa routes should not encode business tenancy in their path.
- 1b. The logging context currently stores owner_id as a ContextVar alongside tenant_id and user_id. After the refactor, the triple becomes owner_id + inbox_id + user_id. Should owner_id remain in Wappa's logging context, or should Wappa only log inbox_id + user_id and leave owner attribution to the host app?
My rec: Keep owner_id in the context system as an optional, externally-supplied value (set by host middleware, not by Wappa routes). It's useful for log correlation. But it must not be a first-class Wappa concept — no validation, no lookup, no cache scoping.

Answers: 
- So first that {owner_id} at the end is the wp_phone_number_id TODAY, so in reality this value will now be officially named inbox_id ACROSS everywhere...
1a) Its not OwnerMiddlewar but InboxMiddleware, this will detect like -> Aha, this webhook is a message that should go to this inbox on this platform/provider -> Right now is Whatsapp mainly, but in the future this could parse the id of a TelegramChannel or bot..
1b) what today is named {owner_id} or {tenant_id} will from now on be named {inbox_id}
---
2. Route Shape — The {provider} Rename and Verify Endpoint

Your PRD proposes:
GET  /webhook/inboxes/{inbox_id}/{provider}
POST /webhook/inboxes/{inbox_id}/{provider}
GET  /webhook/inboxes/{inbox_id}/{provider}/status
GET  /webhook/messenger/{provider}/verify

Questions:

- 2a. The verify endpoint keeps /webhook/messenger/{provider}/verify — why not /webhook/inboxes/verify/{provider}? Meta's verification callback hits a single URL per app (not per inbox). Is verify intentionally inbox-agnostic?
My rec: Yes, verification is app-level, not inbox-level. Meta sends the verify challenge to one URL. But messenger is the old route prefix. I'd use /webhook/verify/{provider} — simpler, no legacy naming.
- 2b. The PlatformType enum has values whatsapp, telegram, teams, instagram. Should the enum itself be renamed to ProviderType since the PRD canonicalizes "Provider" as the term? Or does PlatformType stay internal and only the route param uses {provider}?
My rec: Rename to ProviderType. If you're breaking everything anyway and "provider" is the canonical term, the enum should match. PlatformType
survives only as a git artifact.
- 2c. The current route factory is create_webhook_router(event_dispatcher). Should it become create_inbox_router(event_dispatcher) or stay named after its function (create_webhook_router)?
My rec: Keep create_webhook_router — it describes what the function does (creates webhook routes), not the identity concept it routes to.

Aanswer: 
No we will not use the term {provider} it will remain {platform}, and thats a decission that will and should impact symphonai fields naming as well... Whatsapp is a platform, Teams is a platform, Instagram is a platform...
---
3. InboxBase — How Much Provider Metadata?

Your PRD proposes:
class InboxBase(BaseModel):
    inbox_id: str
    display_address: str | None = None
    provider_account_id: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

Questions:

- 3a. Current TenantBase has business_phone_number_id, display_phone_number, and platform_tenant_id. In the WhatsApp webhook payload, the WABA ID (business account) comes from a different place than the phone_number_id. Does provider_account_id map to the WABA ID? And if so, is it always available in the webhook payload, or only sometimes? 
My rec: provider_account_id = WABA ID for WhatsApp. It's available in the webhook metadata (entry[].id in Meta's payload is the WABA ID). Always
populate it when parsing WhatsApp webhooks.
- 3b. Should InboxBase carry a provider: ProviderType field so downstream consumers know which provider this inbox belongs to without checking the route?
My rec: Yes. Add provider: ProviderType to InboxBase. The model should be self-describing — consumers shouldn't need route context to know what they're looking at.

Answers:
- Its plataform_account_id NOT provider
- Yes WhatsAppBusinessID is the equivalent of platform_account_id, with the platform_inbox_id is what today comes from the env var wp_phone_number_id
- Everything else I AGREE

---
4. bsuid — User Identity vs Inbox Identity
The codebase has 195 references to BSUID. The UserBase.user_id property prefers BSUID over phone_number. Your event envelope includes both user_id and bsuid and phone_number.

Question:

- 4a. In the new envelope, is user_id always the BSUID when available (current behavior), making bsuid and phone_number the raw constituents? Or should the envelope drop bsuid as a top-level field and only have user_id + phone_number (where user_id is BSUID-preferred)?
- My rec: Keep all three in the envelope. user_id is the canonical stable identity (BSUID-preferred), phone_number is the raw contact, bsuid is explicit for consumers that need to distinguish. This matches your PRD envelope exactly. No change needed — just confirming intent.

Answers:
Exactly. Think it this way, user_id in Whatsapp could either be the phone_number (573168227670) OR the BSUID (CO.1234*). If BSUID is present in the payload, then thats the prefered user_id, but still I would like to captura when possible the phone_number (573168227670) for markwting and PII processes around Whatsapp.

---
5. Backlog Docs — Kill or Rewrite?

The backlog/ directory has 5 documents from April-May 2026. Some describe the platform-agnostic webhook abstraction that's already been implemented.

Question:

- 5a. Three of these (platform-agnostic-incoming-webhook-abstraction, platform-agnostic-sse-event-envelope, platform-agnostic-webhook-field-registry)describe architecture that appears to be already landed in wappa/webhooks/core/. Are these stale? Should they be deleted or moved to docs/decisions/ as
historical context?
My rec: Delete the ones that describe already-shipped work. If anything from them is still forward-looking, extract it into a new backlog item withinbox-first language. Don't keep stale guidance that uses tenant_id vocabulary.

Answers:
- Agree. Treat Backlog like a place to store ideas and pending work. IF by doing this we are already completing a Backlog idea, then delete it!

---
6. Single-Context vs Multi-Context — Where Do Docs Live?

Your PRD says create CONTEXT.md at root. But Wappa has sub-domains (messaging, persistence, webhooks, core/sse, core/expiry).

Question:
- 6a. Is Wappa a single bounded context with internal modules, or multiple bounded contexts? This determines whether you get one root CONTEXT.md or a CONTEXT-MAP.md pointing to several.
My rec: Single bounded context. Wappa is one library with one runtime — it's not microservices. The sub-directories are architectural layers, not separate contexts. One root CONTEXT.md is correct. No CONTEXT-MAP.md needed.

ANSWERS:
NO, we need a CONTEST-MAP.md pointing to several as you mentioned, we have messaging, persistance, webhooks, core/sse, core/expirty, core/plugins, even the cli is a different concept

---
7. ARCHITECTURE.md Scope

Question:

- 7a. Should ARCHITECTURE.md describe the library's internal layering (api → core → domain → persistence), or should it describe how a host app
(Symphonai) integrates with Wappa? Or both?
- My rec: Internal layering only. How Symphonai integrates is Symphonai's concern, documented in Symphonai's repo. Wappa's ARCHITECTURE.md shows the dependency direction between layers and the plugin extension points.

Answers:
Agree, in general similar to previous step we should have a general ARCHITECTURE.md explaining HOW a incoming_message webhook or status or whatever each platform sneds gets processed and reaches the WappaEventHandler... and there how WappaEventHandler can use factories like redis or messenger in order to create methods to build conversational apps with wappa... but in each layer fro example persistance I need an Architecture.md going deeper in that context... in this case the root/ARCHITECTURE.md shows the general architecture and the diagram of how messages flow, and the idea on how we will route a message to a whatsapp-platform or instagram-platform context, so in WappaEventHandler we don't have to worry if the message is instagram or whatsapp, wappa handles the context, we just need to define how to process the message and what to reply the user or do with the message, wappa will be incharge of sending a potential reply to the right user in the right platform! And also have a refence directory to refernece to other Architecture.md to go deeper on how each piece of the framework works.
Ideally this should explain how wappa today is WhatsappOpinionated, but changing to a multi-platform events handler framework is not hard, and the abstractions, design-patterns are there.
Important to mention what design-atterns are we using and the logic behind them, etc...

---
8. The Credential Problem — Single-Inbox Hardcode

TenantCredentialsService currently validates against settings.wp_phone_id — it's a single-inbox hardcode dressed up as multi-tenant. The "future: database lookup" comment is still a TODO.

Question:

- 8a. After renaming to InboxCredentialsService, does the implementation stay as a single-inbox settings lookup? Or does this refactor also introduce a proper InboxCredentialStore interface that Symphonai (or any host) can implement?
- My rec: Introduce the interface now (IInboxCredentialStore) with the current settings-based implementation as the default. The refactor is the right moment — you're breaking the contract anyway, and the name change without the interface just kicks the can. The interface is one abstract class with get_access_token(inbox_id) and validate_inbox(inbox_id).

Answers: 
Lets implement the Contract now, so after this we could either handle the inbox_is = settings.wp_phone_id from env vars. OR we could define the process to find the inbox_id in DB and check if exists, maybe using a RedisTableCache in order to avoid hititng db on each message that arrives... THIS one I would like to have a double click here and GO deeper here... So for now, avoid solving this problem in this run.

---
9. File Renames vs Content-Only Renames

Question:

- 9a. tenant_credentials_service.py → should it become inbox_credentials_service.py (file rename), or just rename the class inside? Same question for any module with tenant in the filename.
- My rec: Rename files too. Clean break, no dead paths. tenant_credentials_service.py → inbox_credentials_service.py. The PRD already says "delete old modules." File renames are cheap in a breaking refactor.

Answers:
Rename everything, we should start having a UBIQUITOUS-LANGUAGE across the app and everything should be named accordingly
---
10. Cache Factory — The user_id Stays?

ICacheFactory currently takes (tenant_id, user_id). After the refactor it becomes (inbox_id, user_id).

Question:

- 10a. Is user_id in the cache factory always the BSUID-preferred value from UserBase.user_id? Or is it sometimes a phone number? This matters for cache key stability when a user gets a BSUID assigned after initial contact.
- My rec: Document that user_id in cache scope MUST be the stable identity (BSUID when available). If a user's BSUID becomes known after first contact, the old phone-number-keyed cache is orphaned — that's acceptable and matches the "cold cache" operational note in your PRD.

Answers:
Agree, today the ICacheFactory should move from (tenant_id, user_id) to (inbox_id, user_id), we need to rename this as well everywhere we are missuing the terms tenant_id or owner_id... this renaming process might need double click.. I would like to know in which contexts in wappa we are using tenant_id and owner_id and define because maybe depending on the context tenant_id means owner_id and not inbox_id. So for this one don't focus

---
That's everything. Give me your answers and I'll start writing CONTEXT.md, ARCHITECTURE.md, and the ADR immediately after.

# Notes
So for things related to points 8, 9 and 10. I would like to have an specific session to handle this. Right now lets build SOLID foundations to create this refactoring and start adding the CONTEXT-MAP.md ARCHITECTURE.md and CONTEXT.md across the system!