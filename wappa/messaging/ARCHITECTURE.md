# Messaging Context — Architecture

## Responsibilities

- Implement `IMessenger` for the WhatsApp platform.
- Own the `WhatsAppClient` HTTP adapter: token auth, JSON and multipart POST, GET, DELETE, and streaming GET against the Meta Graph API.
- Own media lifecycle: upload (path / bytes / stream / URL re-upload), download (to disk, temp file, or bytes), stream, delete, and MIME/size validation.
- Own outbound message construction for all WhatsApp message types: text, media, interactive, templates, contacts, locations.
- Own recipient normalization (phone → E.164, BSUID detection) via `schemas.core.recipient`.
- Own read-only template metadata queries against the WABA-level Graph API.
- Keep `Messenger` / `IMessenger` as the public outbound seam for Host Applications.
  Internal WhatsApp handlers may stay grouped by message family, but public
  `TextMessenger`, `MediaMessenger`, or similar seams are deferred until there is
  concrete pressure from multiple platform adapters or tests.

## Not Owned Here

- Webhook parsing and inbound event routing — owned by `core/events`.
- Cache scoping, SSE, or runtime state — owned by `persistence`.
- Credential provisioning and `inbox_id` resolution — owned by `core/config` and API route adapters.
- Business logic, workflow decisions, or event handler behaviour — owned by host applications.
- `IMediaHandler` and `IMessenger` abstract contracts — defined in `domain/interfaces`.

## Module Structure

```
messaging/
  whatsapp/
    client/
      whatsapp_client.py          # HTTP session wrapper; WhatsAppUrlBuilder, WhatsAppManagementUrlBuilder
    handlers/
      whatsapp_media_handler.py   # IMediaHandler impl: upload/download/stream/delete
      whatsapp_interactive_handler.py  # Button menus, list menus, CTA-URL messages
      whatsapp_template_handler.py     # Text, media-header, location-header templates
      whatsapp_specialized_handler.py  # Contact cards, locations, location requests
    messenger/
      whatsapp_messenger.py       # IMessenger impl; composes all four handlers
    models/
      basic_models.py             # MessageResult
      media_models.py             # MediaType enum + supported MIME types
      interactive_models.py       # ReplyButton, ListSection, InteractiveHeader
      template_models.py          # WhatsAppTemplateType, WhatsAppTemplateMediaType, TemplateParameter
      specialized_models.py       # ContactCard
      template_info_models.py     # Request/response models for template read operations
    services/
      whatsapp_template_info_service.py  # Read-only WABA template listing and lookup
    utils/
      error_helpers.py            # handle_whatsapp_error — uniform error → MessageResult
    recipient_resolver.py         # Backward-compat re-export of schemas.core.recipient utilities
```

## Key Classes and Roles

| Class | Role |
|---|---|
| `IMessenger` (`domain/interfaces`) | Abstract outbound messaging contract all platforms must implement. |
| `WhatsAppMessenger` | Facade implementing `IMessenger`. Delegates each message family to the appropriate handler; owns media-source resolution logic. |
| `WhatsAppClient` | Single httpx session per inbox. Holds `phone_number_id` (= `inbox_id`). Used by all handlers and the template info service. |
| `WhatsAppMediaHandler` | Implements `IMediaHandler`. Handles all media upload paths and download paths; enforces WhatsApp MIME and size limits. |
| `WhatsAppInteractiveHandler` | Builds and validates interactive payloads; enforces WhatsApp character-count and structural limits inline before dispatch. |
| `WhatsAppTemplateHandler` | Builds template component trees; resolves marketing vs. standard send URL via `_resolve_template_send_url`. |
| `WhatsAppSpecializedHandler` | Sends contact cards, location pins, and location-request messages. |
| `WhatsAppTemplateInfoService` | Stateless read service for WABA-scoped template metadata. Uses `WhatsAppManagementUrlBuilder`. |
| `MessageResult` | Uniform result VO returned by every send method. |

## Design Patterns

- **Composition over inheritance**: `WhatsAppMessenger` holds handler instances injected at construction; it does not extend them.
- **Dependency injection**: `WhatsAppClient` and `httpx.AsyncClient` are injected, enabling per-inbox isolation and testability.
- **Value objects for URLs**: `WhatsAppUrlBuilder` and `WhatsAppManagementUrlBuilder` are stateless URL factories, not services.
- **Strategy pattern for media source**: `_resolve_media_object` in `WhatsAppMessenger` selects URL-link, media-ID, or upload path based on the shape of the input.
- **Result object**: All send methods return `MessageResult` rather than raising; error details are captured in the result.

## Data Flow — Outbound Message

```
Host application
  → WhatsAppMessenger.send_*(recipient, ...)
      → recipient normalized via schemas.core.recipient.apply_recipient_to_payload
      → factory builds API payload dict
      → handler validates constraints (character limits, required fields)
      → WhatsAppClient.post_request(payload)
          → httpx POST to Graph API
      → MessageResult.from_response_payload(response)
  ← MessageResult returned to host application
```

## Data Flow — Media Upload (file path)

```
WhatsAppMessenger._resolve_media_object(path, ...)
  → WhatsAppMediaHandler.upload_media(path)
      → MIME detection + size validation
      → WhatsAppClient.post_request(multipart form, media endpoint)
  ← MediaUploadResult with media_id
→ payload assembled with {"id": media_id}
→ WhatsAppClient.post_request(message payload)
```

## inbox_id Mapping

`WhatsAppClient.phone_number_id` is the `inbox_id` for the WhatsApp platform. It flows into every `MessageResult` and `MediaUploadResult` as `inbox_id`. The mapping is explicit: `inbox_id == phone_number_id` for all WhatsApp operations.
