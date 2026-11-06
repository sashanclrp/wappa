# Messaging Context — Glossary

Terms specific to this bounded context. Shared kernel terms (`inbox_id`, `user_id`, `Messenger`, `Platform`) are defined in root `CONTEXT.md` and not repeated here.

| Term | Definition |
|---|---|
| **Media Source** | The three forms a media reference can take when passed to the Messenger: a file-system path (uploaded on the fly), a public URL (referenced inline), or an existing WhatsApp media ID (reused directly). |
| **Media ID** | An opaque identifier returned by the WhatsApp Media API after a successful upload. Scoped to the inbox that uploaded it. |
| **Message Family** | Internal grouping of related message operations: text, media, interactive, template, or specialized. Used to organize handler composition inside platform adapters. Not a public seam boundary. |
| **Platform Adapter** | Platform-specific implementation of webhook parsing and outbound message delivery (e.g., WhatsApp adapter). Each adapter implements `IMessenger` as a single facade over its internal handler composition. |
| **Recipient** | The native Delivery Address in a Direct Message Target, normalized within the Platform adapter before transport. |
| **BSUID** | WhatsApp Business Scoped User ID, an alternative Delivery Address to a phone number. |
| **WhatsApp Interactive Message** | A WhatsApp Interactive Message variant such as reply buttons, a list, or a CTA-URL button, distinct from a WhatsApp Template. |
| **WhatsApp Template** | The WhatsApp-specific approved message definition described in the shared glossary; existing Template transport names refer exclusively to this concept. |
| **Button Message** | An Interactive Message presenting text with buttons whose actions follow the Platform's supported button semantics. |
| **Quick Reply** | A predefined reply option whose selection supplies answer text and available action payload to the application. |
| **Message Card** | A structured message item containing supported combinations of image, title, description, and actions. |
| **Message Carousel** | An ordered collection of Message Cards presented together in a message. |
| **Postback** | A Platform interaction event carrying the configured action payload after a person selects a postback action. |
| **Template Transport Request** | A platform-facing request containing exactly one typed Delivery Address, Template identity/category/language, body parameters, an optional typed header, and platform routing policy. Host attribution, Agent context, Campaign facts, Reply State, persistence, usernames, and arbitrary metadata are forbidden. |
| **Template Transport Result** | Safe evidence for one attempted Template call: outcome, Inbox, requested Delivery Address, selected endpoint and routing reason, platform Message ID, returned identity evidence when known, bounded error evidence, request digest, and latency. It is not delivery or Host Application lifecycle evidence. |
| **Template Routing Policy** | The named pre-I/O choice between category-default routing and an explicit Cloud Messages fallback for an eligible marketing Template. It never triggers an automatic cross-endpoint retry. |
| **MessageResult** | The uniform return type for every outbound send operation. Carries `success`, `message_id`, resolved recipient fields, `inbox_id`, platform, and optional error details. |
| **Specialized Message** | Contact cards, locations sent as a point-on-map, and location-request messages. Sent by the adapter's `specialized.py` mixin. |
| **Template Info Service** | A read-only WABA-level helper that queries the Graph API for template metadata — listing, lookup by name, lookup by ID, and namespace resolution. Does not send messages. |
| **WhatsApp Management URL** | Graph API endpoints scoped to the WhatsApp Business Account (WABA ID), used exclusively for template management read operations. Separate from per-inbox messaging endpoints. |
| **URL Builder** | `WhatsAppUrlBuilder` — constructs per-inbox endpoint URLs (messages, media, marketing messages). `WhatsAppManagementUrlBuilder` — constructs WABA-level URLs. Both are value objects, not services. |
