# Wappa owns event meaning and filtering; Hosts own persistence

Accepted, 2026-11-05. Refines ADR-0016 for event lanes whose meaning depends on who sent a message.

## Context

`OutboundEchoWebhook` exists so a Host can see, and store, messages the business sent **outside Wappa**: a person answering from the Instagram app or the WhatsApp Business app. Without it those messages are lost to the Host.

The Platforms differ. WhatsApp Coexistence (`smb_message_echoes`) echoes only messages sent from the Business app or a linked device; Cloud API sends are never echoed. Instagram echoes every outbound message, including the ones Wappa itself sent through the Send API.

Two drafts were rejected:

- Delivering every Instagram echo and letting the Host compare `message_id` with its stored sends. This makes the lane mean different things per Platform, so every Host must re-implement the same filter: an ADR-0016 violation.
- Treating Wappa as the store of conversation history to do the filtering. Wappa does not persist conversations; that is the Host's domain.

## Decision

1. **The lane's meaning is fixed by Wappa, and Wappa enforces it.** `OutboundEchoWebhook` only ever carries messages not sent through a Wappa Messenger. The filter is built in and not configurable. Hosts never filter Wappa's own sends.
2. **Platform evidence first.** When the Platform proves the origin, no state is used: WhatsApp Coexistence echoes are delivered as `BUSINESS_APP`.
3. **Transient correlation, not storage, when evidence is missing.** Instagram echoes carry no sender evidence (verified live on 2026-11-05: an echo of a Wappa send and an echo of a message typed in the Instagram app have the same fields, `mid`, `is_echo` and content, with no `app_id` or `metadata`), so Wappa keeps a `ISentMessageRegistry`: only the IDs of messages it sent, per Inbox, for ten minutes (`TableSentMessageRegistry`, Table Cache, shared across workers on Redis). It is one key per sent message, never one growing object: the Instagram adapter records each confirmed send with a 10-minute TTL; when the echo arrives the Inbound Runtime claims the key, which proves the send and cuts its TTL to a 2-minute grace period (covering a redelivered echo); a send whose echo never arrives expires on its own. The registry therefore holds about the last few seconds of sends. Because an echo can arrive before the send call returns, a miss is re-checked after 1 s and 2 s. This is runtime correlation state like the expiry cache, not a history of conversations.
4. **Never lose a human's message.** If the registry cannot answer (cache outage), the echo is delivered with `origin=UNKNOWN` instead of being dropped.
5. **Hosts own persistence.** Wappa delivers typed events; storing them, merging history backfill, and deduplicating against Host data stay Host responsibilities.

## Consequences

- Every Instagram send through a Wappa Messenger makes one short-lived Table Cache write (`<inbox>:df:wappa_sent_messages:pkid:<message_id>`). A failure there never fails the send.
- Sends that bypass a Wappa Messenger (direct Graph calls by the Host) are not recognised and arrive as `BUSINESS_APP`.
- Verified live on 2026-11-05: the echo `mid` equals the Send API `message_id` (registry hit on the first check, about 0.9 s after the send response), and a message typed in the Instagram app arrives as `BUSINESS_APP` after the 3 s settle window.
- The registry is only shared across processes on Redis. With the memory backend, run one worker; with the JSON backend, one host.
- A genuine human message reaches the Host about 3 s late (the settle window); Wappa's own echoes are usually dropped on the first check.
