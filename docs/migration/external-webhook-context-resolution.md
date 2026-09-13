# Migrating external webhook context resolution

External webhook URLs and events no longer use Inbox identity. Update every
`WebhookPlugin` integration as one clean change.

## Route registration

Before:

```python
WebhookPlugin("mercadopago", include_inbox_id=True, ...)
# POST /webhook/mercadopago/{inbox_id}
```

After, ID-less by default:

```python
WebhookPlugin("mercadopago", ...)
# POST /webhook/mercadopago
```

If the external protocol needs an opaque route value:

```python
WebhookPlugin("github", include_webhook_id=True, ...)
# POST /webhook/github/{webhook_id}
```

Remove environment variables whose only purpose was to put an Inbox ID in an
external callback URL. Webhook ID does not replace them unless the external
protocol itself needs a route identifier.

## Processor

Change `parse_event(request, inbox_id)` to
`parse_event(request, webhook_id: str | None)`. Do not put Inbox or User fields
on `ExternalEvent`. Wappa assigns the authoritative route value to
`event.webhook_id` after parsing.

Move provider authentication into the admission path if it is not already in
`parse_event()`. Raise an explicit FastAPI `HTTPException`, such as a generic
401 for a bad signature, when the sender must receive that failure.

## Context resolution

Delete `IWebhookProcessor.resolve_user_id()`. If handler code needs Inbox
capabilities, implement `IExternalWebhookContextResolver.resolve()` and pass the
strategy as `context_resolver=` on that plugin.

The resolver returns `ResolvedExternalWebhookContext(inbox_ref, user_id)` or
`None`. It runs after processor authentication and may use event payload,
headers, database factories, or trusted `request.state`. Return `None` only when
the event is intentionally Inbox-independent. Resolver failures stop admission.

Inside `process_external_event()`, read resolved identity from `self.inbox_id`
and `self.user_id`, not from the event. Check `self.messenger` and
`self.cache_factory` before using Inbox-scoped capabilities.

## Delivery timing

Wappa now authenticates, parses, resolves context, and builds capabilities
before returning `{"status": "accepted"}`. Only Host handler execution runs in
tracked background work. Review provider retry behavior because admission errors
now reach the sender instead of being logged after a successful response.
