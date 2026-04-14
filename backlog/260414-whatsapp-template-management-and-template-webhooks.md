# WhatsApp Template Management And Template Webhooks

## Context

Wappa currently supports sending WhatsApp templates, but it does not yet support:
- template CRUD operations against Meta Graph API
- lifecycle/status notifications specific to template management
- a dedicated webhook parsing/handling flow for template-related webhook events

`Templates Info` is being implemented separately and is not part of this backlog item.

## Scope

Plan the implementation of:
- template create operations
- template update/modify operations
- template delete operations
- request/response models for CRUD endpoints
- management services for template CRUD
- webhook schema/model support for template lifecycle notifications
- webhook processing and dispatching for template lifecycle events
- API tag surface for `WhatsApp - Template Management`

## Out Of Scope

Not being implemented in this step:
- actual CRUD endpoints and business logic
- actual webhook parsing/dispatch changes for template lifecycle events
- persistence design for template lifecycle history

## Implementation Notes

- Keep management operations separate from phone-number message sending flows.
- Reuse the management-side WABA URL builder, not the phone-number message URL builder.
- Treat template lifecycle webhooks as a separate concern from message delivery statuses.
- Avoid mixing template lifecycle events into the current message `StatusWebhook` shape unless Meta's payloads prove they are structurally identical.

## Proposed Work Breakdown

1. Add management request/response schemas under WhatsApp template management models.
2. Add a dedicated template management service using WABA-level Graph API endpoints.
3. Add API routes under the `WhatsApp - Template Management` tag.
4. Research Meta webhook payloads for template lifecycle events such as `message_template_status_update`.
5. Define dedicated webhook schemas/adapters for template lifecycle notifications.
6. Extend the webhook processor to route template lifecycle events without regressing message/status/error flows.
7. Add tests for CRUD service behavior and webhook parsing/dispatch.

## Open Questions

- Which exact Meta CRUD operations should be exposed in v1: create only, create+delete, or full create/update/delete?
- Should template updates be modeled as PATCH-like high-level operations or as raw Meta-compatible payloads?
- Should template lifecycle events produce a new universal webhook type, or a platform-specific extension attached to the existing webhook system?
- Do we want persistence for template moderation history and quality signals from day one?

## Exit Criteria

- Wappa exposes real template management endpoints backed by Graph API management calls.
- Template management endpoints use typed Pydantic schemas and documented responses.
- Template lifecycle webhook payloads are parsed and routed intentionally.
- API docs expose the management surface under `WhatsApp - Template Management`.
- This backlog file can be deleted because no pending implementation work remains.
