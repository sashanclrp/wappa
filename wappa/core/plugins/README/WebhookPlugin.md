# WebhookPlugin

`WebhookPlugin` adds callbacks for payment systems, CRMs, operational tools,
and other External Webhook Sources. Messaging Platform callbacks use the
Inbound Runtime instead.

## Basic ID-less callback

ID-less callbacks are the default. This is the right choice when URL identity
has no role in the source protocol.

```python
from fastapi import HTTPException

from wappa import ExternalEvent, HMACSignatureVerifier
from wappa.core.plugins import WebhookPlugin


class MercadoPagoProcessor:
    def __init__(self, verifier: HMACSignatureVerifier) -> None:
        self.verifier = verifier

    def get_source_name(self) -> str:
        return "mercadopago"

    async def parse_event(self, request, webhook_id):
        body = await request.body()
        if not self.verifier.verify(body, request.headers):
            raise HTTPException(401, "Invalid webhook signature")
        data = await request.json()
        return ExternalEvent(
            source="mercadopago",
            event_type=data.get("type", "unknown"),
            payload=data.get("data", {}),
            raw_data=data,
        )


app.add_plugin(
    WebhookPlugin(
        "mercadopago",
        processor=MercadoPagoProcessor(verifier),
        event_handler=handler,
        prefix="/webhook/miia/mercado_pago",
    )
)
```

The callback is `POST /webhook/miia/mercado_pago`. No WhatsApp Inbox appears in
the URL or event.

## Optional Webhook ID

Set `include_webhook_id=True` when the external protocol needs a dynamic route
value:

```python
app.add_plugin(
    WebhookPlugin(
        "github",
        processor=GitHubProcessor(),
        event_handler=handler,
        prefix="/webhook/github",
        include_webhook_id=True,
    )
)
```

This mounts `POST /webhook/github/{webhook_id}`. Wappa passes the value to the
processor and writes it to `ExternalEvent.webhook_id`. It is opaque routing
data, not an Inbox ID or authorization credential.

Each plugin chooses its own route form. One application may combine ID-less and
identified callbacks.

## Context resolver strategy

External events do not carry Inbox or User identity. A Host that needs Wappa
Messenger or cache capabilities supplies an `IExternalWebhookContextResolver`
to that plugin:

```python
from wappa import ResolvedExternalWebhookContext
from wappa.domain.inbox import InboxRef


class PaymentContextResolver:
    async def resolve(self, request, event, db, db_read):
        if event.event_type != "payment.approved":
            return None
        if db_read is None:
            raise RuntimeError("Payment context resolution requires a database")

        async with db_read() as session:
            payment = await find_payment(session, event.payload["id"])

        return ResolvedExternalWebhookContext(
            inbox_ref=InboxRef.whatsapp(payment.external_inbox_id),
            user_id=payment.user_id,
        )


app.add_plugin(
    WebhookPlugin(
        "mercadopago",
        processor=processor,
        event_handler=handler,
        context_resolver=PaymentContextResolver(),
    )
)
```

The resolver runs only after the processor authenticates and parses the request.
It may inspect the parsed event, headers, database state, and trusted
`request.state`. FastAPI dependencies or middleware can prepare request state,
but routing evidence prepared before authentication is not trusted merely
because it sits there.

Returning `None` means deliberate Inbox-independent dispatch. The handler then
gets `db` and `db_read`, when configured, but `self.inbox_id`, `self.user_id`,
`self.messenger`, and `self.cache_factory` remain `None`.

Returning `ResolvedExternalWebhookContext` binds an Inbox and optional User. An
Inbox resolution provides Messenger. A User resolution also provides the
user-scoped Cache Factory.

## Admission behavior

Wappa performs these steps before returning success:

1. Snapshot the exact body.
2. Call `processor.parse_event(request, webhook_id)`.
3. Check that the event source matches the plugin source.
4. Run the optional context resolver.
5. Build the handler context.
6. Submit handler dispatch to tracked background work.

An explicit `HTTPException` from a processor or resolver reaches the sender.
Wappa maps validation or contradictory Inbox context to 400, unavailable Inbox
infrastructure to 503, and unexpected admission failures to 500. Failed
admission schedules nothing. Successful admission returns
`{"status": "accepted"}`; later handler failures are logged and do not change
that response.

## Configuration

| Parameter | Default | Meaning |
|---|---|---|
| `external_source` | required | Source name used for validation, logs, and tags |
| `processor` | required | Authenticates and translates the request |
| `event_handler` | required | Handler prototype cloned for dispatch |
| `prefix` | `/webhook/{external_source}` | Router prefix |
| `methods` | `["POST"]` | Accepted callback methods |
| `include_webhook_id` | `False` | Mount dynamic `/{webhook_id}` when true |
| `context_resolver` | `None` | Optional Host-owned context strategy |
| `**route_kwargs` | none | Extra FastAPI `api_route` arguments |

Every plugin exposes `GET {prefix}/status`. The response reports the callback
URL template and whether it contains `{webhook_id}`.

## Public imports

```python
from wappa import (
    ExternalEvent,
    HMACSignatureVerifier,
    IExternalWebhookContextResolver,
    IWebhookProcessor,
    ResolvedExternalWebhookContext,
)
from wappa.core.plugins import WebhookPlugin
```
