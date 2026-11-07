# A reconnect event may reach a known inactive Inbox

Accepted 2026-11-06, implemented in Wappa. Shipped in 0.34.1. Extends the routing table of [ADR-0023](0023-inbound-webhooks.md).

## Context

A Host that follows Wappa's guidance deactivates an Inbox when `process_inbox_connection` reports `account_offboarded`. WhatsApp routing only delivers to active Inboxes, so once every Inbox under a WABA is inactive, Meta's `account_reconnected` callback was refused with 400 before translation. The lane that exists to restore the account could never run for the account that needed it. Registering a custom field is no workaround, because the field is reserved.

## Decision

`account_reconnected` is the only field routed to a known inactive Inbox. The callback signature is verified first, as for every callback. Routing then proves membership: a phone-addressed event needs an inactive record under the `entry[].id` WABA, and an account-only event fans out to the WABA's active members plus its inactive ones from the Host's source. An unknown Inbox, a member of another account, an Inbox of another Platform with the same raw ID, and an empty account stay 400. A source outage stays 503, so Meta retries.

An inactive delivery has `credentials=None`, so `self.messenger` and the Platform Messengers are `None`. No token is read or decrypted. The Cache Factory and `db` remain, since neither needs Platform credentials. The Host decides whether to restore, commits the active record, calls `refresh_inbox`, and opens `self.scope()` if it needs a Messenger in the same handler.

## Consequences

- `process_inbox_connection` can now run with `self.messenger is None`, on `account_reconnected` only. Handlers on that lane must not assume a Messenger.
- Ordinary messages and `account_offboarded` to an inactive Inbox stay refused. A batch is still validated as a whole, so one refused item rejects the callback, reconnect included.
- Delivery stays at-least-once. A duplicate reconnect reaches the Host again, with a Messenger if the Inbox was already restored, so recovery must be idempotent. A Host failure after acceptance is not retried by Wappa or Meta (200 was already returned); the next reconnect callback or a Host recovery path restores the Inbox.
- An account-only reconnect reads the Host's source on every delivery, because the account index holds active members only. The event is rare enough that this needs no cache.
- `IInboxDirectorySource.list_inboxes_for_platform_account` must return inactive records too, as its contract already states. A source that hides them gets no account-only recovery.
- Resolvers without inactive records, such as legacy mode's settings resolver, keep the port's defaults and behave as before.
- The payload shape comes from Meta's documentation and hand-written tests. No live capture of `account_reconnected` exists yet, so a real reconnect remains an open live check.
