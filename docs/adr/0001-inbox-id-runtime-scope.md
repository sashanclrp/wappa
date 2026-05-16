# ADR-0001: inbox_id as Wappa's Runtime Identity Scope

**Status:** Accepted  
**Date:** 2026-05-16  
**Deciders:** Symphonai Platform Team

## Context

Wappa used `tenant_id` as its core runtime identity across webhook routes, cache namespaces, SSE subscriptions, event envelopes, credential lookup, and messenger factories. The actual value being passed was always the WhatsApp `phone_number_id` — the platform-facing inbox execution identity.

The term "tenant" implies business tenancy (an owning account or organizational boundary), but Wappa does not own business tenancy. Wappa is a messaging runtime that executes against a platform inbox. Business ownership, channels, customers, and workflows belong to the host application.

This mismatch caused:
- Confusion between "who owns this" (business) and "where does this message go" (platform inbox)
- OwnerMiddleware and WebhookController fighting over the same URL segment with different names
- Code comments explaining that `tenant_id` "is actually the phone_number_id"
- Inability to cleanly separate Wappa's runtime scope from host application concerns

## Decision

Replace `tenant_id` with `inbox_id` as Wappa's core runtime identity. An Inbox is the platform-facing message ingress/egress identity.

Specifically:
- **`inbox_id`** is the stable Wappa identifier for a platform inbox. For WhatsApp, `inbox_id == Meta phone_number_id`.
- **Platform** remains the canonical term for external messaging services (WhatsApp, Telegram, etc.). `PlatformType` enum unchanged.
- **`platform_account_id`** identifies the platform-side account grouping inboxes (WABA ID for WhatsApp). Metadata, not runtime identity.
- **`owner_id`** becomes optional host-supplied metadata for log correlation only. Not a Wappa routing, caching, or credential concept.

## Consequences

### Breaking changes (intentional, no compatibility layer)
- Webhook routes: `/webhook/messenger/{tenant_id}/{platform}` → `/webhook/inboxes/{inbox_id}/{platform}`
- Event envelopes: `"tenant_id"` field → `"inbox_id"` field
- Cache key namespaces: `{tenant}:...` → `{inbox}:...` (existing cache data orphaned; flush on deploy)
- SSE subscriptions: filter by `inbox_id` not `tenant_id`
- Public classes: `TenantBase` → `InboxBase`, `TenantCredentialsService` → `InboxCredentialsService`
- Handler context: `self.tenant_id` → `self.inbox_id`

### What stays the same
- `PlatformType` enum name and values unchanged
- `user_id` semantics unchanged (BSUID-preferred)
- `WappaEventHandler` processor method signatures unchanged (only injected context field renames)
- Plugin interfaces unchanged
- CLI scaffolding commands unchanged

### Operational impact
- Redis and JSON cache namespaces change destructively. Deploy requires cache flush or acceptance of cold cache.
- External Wappa apps using `tenant_id` routes/fields/classes will break.
- Host applications (Symphonai) must update their Wappa adapter in the same delivery window.

## Alternatives Considered

1. **Keep `tenant_id` but document it means "inbox"** — Rejected. Names shape thinking; "tenant" will keep pulling toward business tenancy concerns that don't belong in Wappa.

2. **Rename to `channel_id`** — Rejected. "Channel" is Symphonai's term (Owner → Channel → Inbox). Wappa should not encode the host app's domain model.

3. **Add `inbox_id` as alias, deprecate `tenant_id` gradually** — Rejected. Dual naming creates confusion, dual envelope fields create integration ambiguity, and the codebase is small enough for a clean break.

4. **Use `phone_number_id` directly** — Rejected. Platform-specific. When Telegram support lands, the inbox identity won't be a phone number.
