# Template Message API Flow Guide

## Overview

This guide explains how template messages flow through the Wappa API system and how to properly configure payloads for the `/api/whatsapp/templates/send-media` endpoint.

## API Flow Architecture

```
API Request → FastAPI Route → Messenger.send_media_template() → WhatsApp API
                    ↓
            @dispatch_message_event decorator
                    ↓
            APIMessageEvent created with request_payload
                    ↓
            APIEventDispatcher.dispatch()
                    ↓
            WappaEventHandler.process_api_message(event)
```

## Request Payload Structure

### Correct Media Template Payload

```json
{
  "recipient": "573168227670",
  "template_name": "260119_revival_campaign",
  "language": {
    "code": "es_CO"
  },
  "media_type": "video",
  "media_url": "https://zzbumvtvtonqlilblaqk.supabase.co/storage/v1/object/public/30x-wappa/template_campaigns/260120_revival/XtremeSales.mp4",
  "body_parameters": [
    {
      "type": "text",
      "text": "Sasha",
      "parameter_name": "lead_first_name"
    }
  ],
  "state_config": {
    "state_value": "revival_campaign_response",
    "ttl_seconds": 3600,
    "initial_context": {
      "campaign_id": "260119_revival",
      "template_sent_at": "2025-01-21T07:00:00Z"
    }
  },
  "template_metadata": {
    "text_content": "This is a revival campaign video targeting inactive leads",
    "media_description": "High-energy sales video with product showcase",
    "media_transcript": "Welcome back! We have exciting offers...",
    "system_message": "User received revival campaign. Focus on re-engagement and conversion."
  }
}
```

### ⚠️ IMPORTANT: Media Field Rules

**MUST provide exactly ONE of:**
- `media_id` (for uploaded media) OR
- `media_url` (for external media)

**NEVER provide both** - validation will fail.

```json
// ✅ CORRECT - media_url only
{
  "media_type": "video",
  "media_url": "https://example.com/video.mp4"
}

// ✅ CORRECT - media_id only
{
  "media_type": "video",
  "media_id": "12345678"
}

// ❌ INCORRECT - both provided
{
  "media_type": "video",
  "media_id": "12345678",
  "media_url": "https://example.com/video.mp4"
}

// ❌ INCORRECT - neither provided
{
  "media_type": "video"
}
```

## Field Details

### 1. Basic Fields (Required)

#### `recipient` (string)
- Phone number without '+' (10-15 digits)
- Example: `"573168227670"`

#### `template_name` (string)
- WhatsApp-approved template name
- Example: `"260119_revival_campaign"`

#### `language` (object)
- BCP-47 language code
- Common codes: `es`, `en_US`, `pt_BR`, `es_CO`, `es_MX`
- Example: `{"code": "es_CO"}`

#### `media_type` (string)
- Must be: `"image"`, `"video"`, or `"document"`
- Determines header type

### 2. Body Parameters (Optional)

Array of template parameter replacements:

```json
"body_parameters": [
  {
    "type": "text",
    "text": "Sasha",
    "parameter_name": "lead_first_name"
  },
  {
    "type": "text",
    "text": "30X Sales Program",
    "parameter_name": "product_name"
  }
]
```

**Fields:**
- `type`: Must be `"text"` for template body parameters
- `text`: The replacement value (max 1024 chars)
- `parameter_name`: Optional explicit binding to template variable (alphanumeric + underscore, must start with letter)

**Limits:**
- Max 10 parameters per template
- Max 1024 characters per parameter

### 3. State Config (Optional)

Enables routing subsequent user responses to specific handlers:

```json
"state_config": {
  "state_value": "revival_campaign_response",
  "ttl_seconds": 3600,
  "initial_context": {
    "campaign_id": "260119_revival",
    "template_sent_at": "2025-01-21T07:00:00Z",
    "user_segment": "inactive_leads"
  }
}
```

**How it works:**
1. When template is sent successfully, creates cache entry: `template-{state_value}`
2. Entry scoped to recipient's phone number
3. Handler can retrieve state when user responds
4. Enables context-aware response handling

**Fields:**
- `state_value` (required): Alphanumeric + dashes/underscores (1-128 chars)
- `ttl_seconds` (default: 3600): State lifetime (60-86400 seconds / 1 min - 24 hours)
- `initial_context` (optional): Custom data to store with state

**Usage in Handler:**
```python
async def process_message(self, webhook: IncomingMessageWebhook):
    # Check if user has active template state
    cache = self.cache_factory.get_cache("user_cache")
    state = await cache.get("template-revival_campaign_response",
                           scope=webhook.user.user_id)

    if state:
        # User responding to revival campaign template
        campaign_id = state.get("campaign_id")
        # Handle response with context...
```

### 4. Template Metadata (Optional)

**⚠️ CRITICAL: This metadata is NOT sent to WhatsApp!**

Internal-only data for AI agent context and analytics:

```json
"template_metadata": {
  "text_content": "This is a revival campaign video targeting inactive leads",
  "media_description": "High-energy sales video with product showcase",
  "media_transcript": "Welcome back! We've missed you! Check out these exclusive offers...",
  "system_message": "User received revival campaign template. Focus on re-engagement strategies and conversion tactics."
}
```

**Fields:**
- `text_content` (max 4096 chars): Summary of template content for AI context
- `media_description` (max 2048 chars): Description of media content
- `media_transcript` (max 10000 chars): Text transcription of video/audio (only for video/audio types, NOT for images)
- `system_message` (max 8192 chars): System-level instructions for AI agent processing

**When to use:**
- Building AI-powered conversation systems
- Need context about what was sent to user
- Analytics and tracking purposes
- Training conversational AI on sent content

**Important Notes:**
- Metadata goes to `APIMessageEvent.request_payload` but never to WhatsApp API
- Available in `process_api_message(event)` handler method
- `media_transcript` will raise validation error if used with `media_type: "image"`

## Handler Implementation

### Accessing Template Data in process_api_message()

```python
from wappa import WappaEventHandler
from wappa.domain.events.api_message_event import APIMessageEvent

class MyHandler(WappaEventHandler):
    async def process_api_message(self, event: APIMessageEvent) -> None:
        """
        Called after template is sent via API.

        event.request_payload contains the ENTIRE MediaTemplateMessage,
        including template_metadata and state_config.
        """
        # Extract template metadata (internal only, not sent to WhatsApp)
        template_metadata = event.request_payload.get("template_metadata")
        if template_metadata:
            text_content = template_metadata.get("text_content")
            media_description = template_metadata.get("media_description")
            media_transcript = template_metadata.get("media_transcript")
            system_message = template_metadata.get("system_message")

            self.logger.info(f"Template context: {text_content}")

            # Use for AI agent context, analytics, etc.
            if system_message:
                # Pass to AI agent for processing context
                await self._update_ai_context(event.recipient, system_message)

        # Extract state config (if provided)
        state_config = event.request_payload.get("state_config")
        if state_config:
            state_value = state_config.get("state_value")
            initial_context = state_config.get("initial_context")

            self.logger.info(f"State '{state_value}' set for {event.recipient}")

            # State is automatically created by TemplateStateService
            # Handler can retrieve it when user responds

        # Extract body parameters with parameter_name
        body_parameters = event.request_payload.get("body_parameters", [])
        for param in body_parameters:
            param_name = param.get("parameter_name")
            param_value = param.get("text")
            self.logger.debug(f"Parameter {param_name}: {param_value}")

        # Track in analytics/database
        if self.db:
            async with self.db() as session:
                # Store sent template for tracking
                await self._track_template_sent(
                    session,
                    recipient=event.recipient,
                    template_name=event.request_payload.get("template_name"),
                    message_id=event.message_id,
                    success=event.response_success,
                )
```

### Handling User Responses with State

```python
async def process_message(self, webhook: IncomingMessageWebhook) -> None:
    """
    Handle incoming messages from users.
    Check for active template state to provide context-aware responses.
    """
    user_id = webhook.user.user_id
    cache = self.cache_factory.get_cache("user_cache")

    # Check if user has active template state
    state = await cache.get("template-revival_campaign_response", scope=user_id)

    if state:
        # User is responding to revival campaign template
        campaign_id = state.get("campaign_id")
        template_sent_at = state.get("template_sent_at")

        self.logger.info(
            f"User {user_id} responding to campaign {campaign_id} "
            f"sent at {template_sent_at}"
        )

        # Handle response with context
        await self._handle_revival_campaign_response(webhook, state)

        # Clear state after handling (optional)
        await cache.delete("template-revival_campaign_response", scope=user_id)
    else:
        # Handle as regular message
        await self._handle_regular_message(webhook)
```

## Complete Example: Revival Campaign

### 1. Send Template via API

```bash
curl -X 'POST' \
  'https://api.example.com/api/whatsapp/templates/send-media' \
  -H 'Content-Type: application/json' \
  -d '{
  "recipient": "573168227670",
  "template_name": "260119_revival_campaign",
  "language": {"code": "es_CO"},
  "media_type": "video",
  "media_url": "https://storage.example.com/campaigns/revival.mp4",
  "body_parameters": [
    {
      "type": "text",
      "text": "Sasha",
      "parameter_name": "lead_first_name"
    },
    {
      "type": "text",
      "text": "30X Sales",
      "parameter_name": "program_name"
    }
  ],
  "state_config": {
    "state_value": "revival_response",
    "ttl_seconds": 7200,
    "initial_context": {
      "campaign_id": "260119_revival",
      "user_segment": "inactive_30_days",
      "offer_code": "REVIVAL30"
    }
  },
  "template_metadata": {
    "text_content": "Revival campaign for 30-day inactive leads with special offer",
    "media_description": "Product demo video showcasing new features",
    "media_transcript": "Hi {{lead_first_name}}! Welcome back to {{program_name}}...",
    "system_message": "Revival campaign sent. User was inactive for 30 days. Offer code REVIVAL30 valid for 48 hours. Focus on re-engagement and addressing previous objections."
  }
}'
```

### 2. Track in process_api_message()

```python
async def process_api_message(self, event: APIMessageEvent) -> None:
    # Log the template send
    metadata = event.request_payload.get("template_metadata", {})
    self.logger.info(
        f"Revival campaign sent to {event.recipient}: "
        f"{metadata.get('text_content')}"
    )

    # Store in analytics database
    if self.db and event.response_success:
        async with self.db() as session:
            from .models import CampaignDelivery

            delivery = CampaignDelivery(
                recipient=event.recipient,
                campaign_id="260119_revival",
                template_name=event.request_payload["template_name"],
                message_id=event.message_id,
                ai_context=metadata.get("system_message"),
                delivered_at=event.timestamp,
            )
            session.add(delivery)
```

### 3. Handle User Response with State

```python
async def process_message(self, webhook: IncomingMessageWebhook) -> None:
    user_id = webhook.user.user_id
    cache = self.cache_factory.get_cache("user_cache")

    # Check for revival campaign state
    state = await cache.get("template-revival_response", scope=user_id)

    if state:
        message_text = webhook.get_message_text().lower()
        offer_code = state.get("offer_code")

        if "interesado" in message_text or "si" in message_text:
            await self.messenger.send_text(
                text=f"¡Excelente! Tu código de descuento es: {offer_code}",
                recipient=user_id
            )
            # Track conversion
            await self._track_campaign_conversion(user_id, state)
        else:
            # Handle objections or questions
            await self._handle_campaign_inquiry(webhook, state)
```

## Testing with OpenAPI/Swagger

When testing in the interactive docs, the OpenAPI schema shows example values for all fields. **Important notes:**

1. **Remove either `media_id` OR `media_url`** - OpenAPI shows both, but you must use only one
2. You can omit `state_config` and `template_metadata` entirely if not needed
3. The `parameter_name` field in `body_parameters` is optional

**Minimal working payload:**
```json
{
  "recipient": "573168227670",
  "template_name": "my_template",
  "language": {"code": "es"},
  "media_type": "image",
  "media_url": "https://example.com/image.jpg"
}
```

**Full-featured payload:**
```json
{
  "recipient": "573168227670",
  "template_name": "my_template",
  "language": {"code": "es_CO"},
  "media_type": "video",
  "media_url": "https://example.com/video.mp4",
  "body_parameters": [
    {"type": "text", "text": "John", "parameter_name": "first_name"}
  ],
  "state_config": {
    "state_value": "awaiting_response",
    "ttl_seconds": 3600,
    "initial_context": {"source": "campaign_a"}
  },
  "template_metadata": {
    "text_content": "Welcome video",
    "system_message": "New user onboarding video sent"
  }
}
```

## Common Pitfalls

### ❌ Validation Errors

**Error: "Either media_id or media_url must be provided, but not both"**
- **Cause:** Both fields provided or neither provided
- **Fix:** Include exactly one: `media_id` OR `media_url`

**Error: "media_transcript field is not supported for image media type"**
- **Cause:** `media_transcript` provided with `media_type: "image"`
- **Fix:** Only use `media_transcript` for video/audio types

**Error: "Invalid language code format"**
- **Cause:** Language code not BCP-47 compliant or unsupported
- **Fix:** Use standard codes: `es`, `en_US`, `pt_BR`, `es_CO`, etc.

### ⚠️ State Management

- State is scoped to recipient (user-specific)
- State automatically expires after `ttl_seconds`
- State only created if template sends successfully (`result.success == True`)
- Check state existence before accessing to avoid KeyError

### 📊 Metadata vs State

**template_metadata:**
- Internal only, NOT sent to WhatsApp
- For AI context and analytics
- Captured in `event.request_payload`
- Available in `process_api_message()`

**state_config:**
- Creates cache entry for routing responses
- Scoped to recipient
- Has TTL (expires automatically)
- Retrieved in `process_message()` when user responds

## API Response

Successful response:
```json
{
  "success": true,
  "message_id": "wamid.HBgNNTczMTY4MjI3NjcwFQIAEhggMUI3...",
  "error": null,
  "raw_response": {
    "messaging_product": "whatsapp",
    "contacts": [...],
    "messages": [...]
  }
}
```

Failed response:
```json
{
  "success": false,
  "message_id": null,
  "error": "Template not found or not approved",
  "raw_response": null
}
```

## Summary Checklist

- [ ] Provide exactly ONE of: `media_id` or `media_url`
- [ ] Use valid `media_type`: `image`, `video`, or `document`
- [ ] Language code is BCP-47 compliant
- [ ] Body parameters use `type: "text"` (max 10 parameters)
- [ ] `parameter_name` is alphanumeric + underscore, starts with letter
- [ ] State value is alphanumeric + dashes/underscores (1-128 chars)
- [ ] TTL is 60-86400 seconds (1 min to 24 hours)
- [ ] Template metadata is optional (internal use only)
- [ ] No `media_transcript` for image types
- [ ] Handler implements `process_api_message()` to track sent templates
- [ ] Handler checks state in `process_message()` for context-aware responses
