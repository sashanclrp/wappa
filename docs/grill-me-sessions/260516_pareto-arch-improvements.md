Before I write the 4 PRDs, answer these in one shot. I’ll use your answers to keep CONTEXT.md, local context docs, and the PRDs consistent.

Planned PRDs

  1. Deep inbound runtime module.
  2. Consolidate schemas vs webhooks.
  3. Finish Inbox language cleanup.
  4. Keep or reshape the IMessenger seam.

# Language Questions

1. For the module that owns webhook orchestration, should the canonical term be Inbound Runtime?
Recommended: Inbound Runtime = the Wappa module that turns an accepted platform webhook into a context-bound handler dispatch. Avoid “Webhook Service” because it hides that this includes Inbox/User context, Messenger, Cache Factory, DB sessions, SSE scope, and dispatch. -> Agree we named in wappaEventHandler as InboundMessageWebhook, we should change this and use InboundMessageWebhook, so we have only ONE way of naming this... please add this to the CONTEXT.md needed (root and specific) and even an adr

2. For the object produced by that module, should the term be Dispatch Context?
Recommended: Dispatch Context = the per-event runtime bundle containing inbox_id, user_id, messenger, cache_factory, DB access, SSE identity, and the cloned WappaEventHandler. Avoid “Request Context” because the async background task may outlive the HTTP request. -> AGREE

3. Should Processor mean “pure platform payload translator” only?
Recommended: Yes. A Processor parses a platform webhook payload into a Universal Model. It must not mutate ContextVars, build messengers, resolve cache factories, or clone handlers. -> AGREE

4. For inbox_id conflicts between URL and payload metadata, which source wins?
Recommended: URL inbox_id is the routing authority. Payload phone_number_id is validated against it when present. If they differ, treat it as a
rejected/mismatched webhook, not a silent override. -> AGREE, here this commit work Commit: 54373d5 Message: [ADD] [CONTRACT] Support database inbox credential store, when enabled should be the source of truth, we get the inbox_id from webhook and try to find in db/cache depending on the implementation for exampel in symphonai, if the inbox_id matches any of the registered inbox_ids... 

5. For WhatsApp platform_account_id, should it always mean WABA ID?
Recommended: Yes. Platform Account for WhatsApp means WABA ID (entry[].id). phone_number_id maps to inbox_id, never platform_account_id. -> AGREE, 100%

6. What should we call the canonical inbound models package?
Recommended: Webhook Models owned by wappa/webhooks. wappa/schemas should keep shared primitives/request models or become compatibility shims. Avoid “schemas” for inbound webhook models because it currently creates two competing sources of truth. -> Disagree, we should have pydantic schemas for EVERY WEBHOOK, WHY? because in the future when we add Telegram, we need to translate whatever telegram payloads are into the SAME UNIVERSAL WEBHOOKS, now today by design this WEbhooks are designed Whatsapp first, so in practice what should happen is we must accomoadte any ffuture platform into this UniversalWEbhook forms...

7. Should Universal Model stay the canonical term?
Recommended: Yes. A Universal Model is the platform-agnostic webhook representation that leaves wappa/webhooks and enters dispatch. -> AGREE

8. Should Compatibility Shim be an accepted term for old import paths?
Recommended: Yes. Compatibility Shim = a module that preserves legacy import paths while delegating to the canonical module, with no domain behavior of its own. -> I don't understand this, WE should not allow old import paths, we should have a CLEAN breaking change, no compatibilyt -> PLEASE CHECK WHERE ELSE we are having compatibility patches, we MUST DELETE, and have a clean clear framework to work from now ON. If apps using wappa breks thats THE IDEA, they SHOULD and MUST adapt to the new WAPPA.

9. Should “Provider” remain forbidden for messaging platforms?
Recommended: Yes for Wappa messaging. Use Platform for WhatsApp/Telegram/etc. Allow External Webhook Source or External Source for MercadoPago/Stripe-style non-messaging webhooks, because “provider” is currently overloaded. -> AGREE external webhok sources might have PaymentProviders like MercadoPago or Stripe or Wompi...

10. For the wide IMessenger, should we name the current seam Messenger and defer smaller seams?
Recommended: Yes. Keep Messenger as Wappa’s outbound message interface for Host Applications. Do not introduce TextMessenger, MediaMessenger, etc. until there are at least two real platform adapters or a concrete testing pain. -> AGREE, though Telegram, Instagram work very similar webhook and API wise to Whatsapp... we have an IMessenger fatory and internally we define depedning on the type of messages a category...

11. Should the fourth PRD be “defer Messenger split” rather than “refactor Messenger”?
Recommended: Yes. The architectural improvement is documenting the decision not to split a hypothetical seam yet, plus maybe tightening internal
WhatsApp modules without changing the public Messenger interface. -> AGREE. But again this should be the BEST architectural design decision, if this is a breaking change so be it. I want a Clean upgrade Wappa after this... I'll handle the aftermath on the apps using wappa later. THATS OK WITH ME!

12. Should the PRDs update docs only, or also propose code changes?
Recommended: PRDs only. Each should define WHY / WHAT / WHAT NOT / HOW, ubiquitous language, acceptance criteria, and affected files, but not modify implementation yet. -> AGREE

# Note
Please include on the PRD a yaml style metadata indicating which models could do the Job wiht 100% efficacy if GPT5.5 or GPT5.4 or GPT5.3-code or which ones can we delegate to inferior yet useful Claude Opus 4.6 or Sonnet 4.6