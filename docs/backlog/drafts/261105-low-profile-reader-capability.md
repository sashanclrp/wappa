---
status: draft
origin: ADR-0016 contract map (2026-11-05)
---

# `IProfileReader`: read the business profile on every Platform

A shared capability (ADR-0016 contract map) that returns the connected Inbox's own public profile in one shape, so Hosts can show "connected as …" and check setup without Platform branches.

| Platform | Source |
| --- | --- |
| WhatsApp | `/{phone_number_id}` (display number, verified name, quality, name status) + `/{phone_number_id}/whatsapp_business_profile` (about, description, address, email, websites, picture) |
| Instagram | `/{ig_id}?fields=username,name,profile_picture_url,biography,website,followers_count` |
| Telegram | `getMe` + `getMyDescription` |

Proposed: `get_profile() -> ReadResult[InboxProfile]`, where `InboxProfile` has `display_name`, `handle`, `picture_url`, `description` and `website`, plus a Platform-specific `extras` mapping for fields like WhatsApp quality rating. Writing the profile (`update_profile`) is a later, separate decision.

Exit: implemented for WhatsApp and Instagram with tests; used by the example app's `/whoami`.
