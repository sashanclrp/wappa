# One cache namespace rule for every Platform; the Inbox Directory cache resets at startup

Accepted, 2026-11-05. Amends the WhatsApp exception in `InboxRef.cache_namespace` (0.27 multi-Inbox work) and the freshness rules of [ADR-0011](0011-encrypted-inbox-directory.md).

## Context

Since 0.27 every Inbox-scoped key starts with `InboxRef.cache_namespace`. WhatsApp kept the raw `phone_number_id` so keys deployed before multi-Inbox stayed readable, while every new Platform was qualified (`instagram__<id>`). The result was two rules in one namespace and a visible inconsistency in Redis (`1014417365082534` next to `instagram__1784…`).

Separately, a live test showed that restarting Wappa did not apply a token rotated in the Host source. The Inbox Directory caches active rows in Redis with a sliding 60-minute TTL renewed on every read, and Redis survives restarts, so the old token kept serving while messages kept arriving.

0.34 already breaks the public contract (ADR-0016, ADR-0019), so Hosts migrate once.

## Decision

1. **Every Platform uses `<platform>__<inbox_id>`, WhatsApp included.** `InboxRef.cache_namespace` has no Platform exception. `InboxRef.from_cache_namespace` rejects an unqualified namespace instead of assuming WhatsApp.
2. **A one-off, explicit migration renames pre-0.34 keys.** `wappa migrate cache-namespaces -i <phone_number_id> ...` renames `<pnid>:*` to `whatsapp__<pnid>:*` in every Wappa Redis database (and `<pnid>_*.json` files for the JSON backend). It is a dry run unless `--apply`; Redis `RENAMENX` keeps TTLs and never overwrites. The operator names the WhatsApp Inboxes: nothing is inferred from key shapes, because Table Cache accepts Host-defined `context_id` values that may be numeric.
3. **The Inbox Directory cache resets at startup in explicit routing.** A startup hook (priority 25, after cache infrastructure) deletes only Wappa's two directory tables under the reserved System Scope (`__system__:df:wappa_inbox_directory:pkid:*` and its account index). No other table, scope or database is touched. Inboxes reload lazily from the Host source on first use, so startup does not read the source and several workers restarting together do not stampede it.
4. **Runtime changes stay the Host's call.** A record changed while Wappa runs (token rotation, deactivation) still needs `InboxDirectory.refresh_inbox(inbox_ref)` after the Host commits it. The startup reset only covers changes made while Wappa was down.

## Consequences

- Deploy order for 0.33 Hosts: stop workers, run the migration, start 0.34. Skipping it hides state, user, Inbox-scoped table and AI-state data and orphans pending expiry timers.
- Pub/Sub channels change to `wappa:notify:whatsapp__<pnid>:...`; subscribers update their pattern in the same deploy.
- The first message per Inbox after a restart costs one source read, the same path as any cache miss.
- Rejected: reloading every Inbox at startup (source reads proportional to Inbox count on every boot, and a source outage would block startup); keeping the WhatsApp exception (two rules forever).
