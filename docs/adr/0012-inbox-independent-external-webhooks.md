# ADR-0012: Inbox-independent external webhooks

## Status

Accepted on 2026-09-13.

## Decision

External Webhook Source callbacks are ID-less by default. A plugin may expose a
dynamic Webhook ID, but that opaque route value never identifies or authorizes
an Inbox. `ExternalEvent` therefore carries no Inbox or User identity.

A Host may attach an `IExternalWebhookContextResolver` strategy to each plugin.
After the processor authenticates and parses the request, the resolver may use
the event, headers, database state, or trusted FastAPI request state to return a
concrete `InboxRef` and optional User. Returning `None` means deliberate
database-only dispatch. Wappa finishes authentication and context resolution
before acknowledging the sender, then runs only the Host handler in background
work.

## Why

The previous URL contract reused `inbox_id` as a convenient context lookup key.
That forced unrelated payments and operational events to depend on WhatsApp
route construction and made callback URLs change when runtime Inboxes changed.
Making Inbox identity optional on the event would preserve the same category
error. Routing identity and runtime messaging context are separate concepts.

The resolver strategy keeps business mappings in the Host. Fixed header names,
payload paths, and database relations do not belong in Wappa.

## Consequences

- `include_inbox_id`, `IWebhookProcessor.resolve_user_id`, and the Inbox and User
  fields on `ExternalEvent` are removed as a clean breaking change.
- A User can only appear in a resolution that also contains an `InboxRef`.
- Middleware may prepare routing evidence, but resolution runs after processor
  authentication. Middleware that resolves privileged context earlier must
  authenticate the request itself.
- Provider authentication or resolver failures can produce an HTTP error and
  never schedule handler work.
