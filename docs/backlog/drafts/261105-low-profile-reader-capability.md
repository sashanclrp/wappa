---
status: draft
origin: ADR-0025 contract map (2026-11-05)
last_reviewed: 2026-11-06
---

# `IInboxProfileReader`: read the business profile on every Platform

## Code reality (2026-11-06)

No shared Inbox business-profile reader was found in Wappa or Symphonai. Symphonai stores selected channel setup fields; its business_profile credential kind is for Google Business Profile. Architecture hardening H-26 reads a messaging User profile, and H-27 only renames this proposal. Neither implements this Inbox-profile scope.

A shared capability (ADR-0025 contract map) that returns the connected Inbox's own public profile in one shape, so Hosts can show "connected as …" and check setup without Platform branches.

| Platform | Source |
| --- | --- |
| WhatsApp | `/{phone_number_id}` (display number, verified name, quality, name status) + `/{phone_number_id}/whatsapp_business_profile` (about, description, address, email, websites, picture) |
| Instagram | `/{ig_id}?fields=username,name,profile_picture_url,biography,website,followers_count` |
| Telegram | `getMe` + `getMyDescription` |

Proposed: `get_profile() -> ReadResult[InboxProfile]`, where `InboxProfile` has `display_name`, `handle`, `picture_url`, `description` and `website`, plus typed optional fields for Platform-specific evidence such as WhatsApp quality rating. Writing the profile (`update_profile`) is a later, separate decision.

Exit: implemented for WhatsApp and Instagram with tests; used by the example app's `/whoami`.
