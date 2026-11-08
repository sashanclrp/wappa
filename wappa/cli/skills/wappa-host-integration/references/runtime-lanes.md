# Runtime lanes: external webhooks, crons and the API

## Contents

- External Webhook Sources
- Crons
- The HTTP API lane
- Choosing a lane for scheduled work

## External Webhook Sources

Receive a third-party webhook (a CRM, a payment provider, a form tool) and handle it in your handler with full Wappa context:

```python
from fastapi import HTTPException
from wappa import ExternalEvent, HMACSignatureVerifier, IWebhookProcessor
from wappa.core.plugins import WebhookPlugin

class CrmProcessor(IWebhookProcessor):
    verifier = HMACSignatureVerifier(os.environ["CRM_WEBHOOK_SECRET"], header="X-Signature", prefix="sha256=")
    def get_source_name(self) -> str:
        return "crm"
    async def parse_event(self, request, webhook_id: str | None) -> ExternalEvent:
        body = await request.body()
        if not self.verifier.verify(body, request.headers):     # never raises; False on any mismatch
            raise HTTPException(status_code=401, detail="bad signature")
        data = json.loads(body)
        return ExternalEvent(source="crm", event_type=data["type"], webhook_id=webhook_id, payload=data)

app.add_plugin(WebhookPlugin("crm", processor=CrmProcessor(), event_handler=handler,
                             context_resolver=CrmContext()))     # optional
```

The route is `POST /webhook/crm` (or `{prefix}/{webhook_id}` with `include_webhook_id=True`), mounted public, so the processor authenticates every request. `webhook_id` is opaque routing data for the provider, never an Inbox. To bind an Inbox and User, give an `IExternalWebhookContextResolver`: `async resolve(request, event, db, db_read) -> ResolvedExternalWebhookContext(inbox_ref=..., user_id=...) | None`. It looks up your own mapping, for example a CRM contact to your User and their Inbox. A `ValueError` from `parse_event` answers 400. A provider with its own signing scheme (timestamps, several signatures) needs its own check in `parse_event`; `HMACSignatureVerifier` covers a plain HMAC header (hex or base64, optional prefix). With a context, `process_external_event(event)` gets `self.messenger` and caches. With `None`, only `self.db` is bound. Route by `event.event_type`, or use `ExternalEventRegistry().on(source, event_type)` and `await registry.dispatch(event)`. Make handlers idempotent: providers retry.

## Scheduled work

Reminders, timers, recurring jobs, heartbeats and crons all run in `process_scheduled_event`, on a handler Wappa has prepared. See the `wappa-scheduled-tasks` skill.

## The HTTP API lane

Sends through Wappa's HTTP API (`/api/{platform}/...`) dispatch `process_api_message(event: APIMessageEvent)` after the send (`message_type`, `message_id`, `recipient`, `request_payload`, `response_success`, `response_error`, `inbox_id`). No Messenger is bound there: use it to record or mirror operator sends, not to reply. The routes take the same neutral request models as the Messenger. A capability the Inbox's Platform lacks answers 501, a long Meta rate limit 429 with `Retry-After`, and a failed send a 4xx. `GET /api/{platform}/interactive/limits` returns the shared limits. Template send routes are off unless `Wappa(include_template_transport_api=True)`.

## Choosing a lane

| Need | Use |
| --- | --- |
| Anything that fires later or repeatedly | `wappa-scheduled-tasks` skill |
| A provider calls you back | External Webhook Source |
| Your backend sends immediately, outside a webhook | `OutboundRuntime.from_app(app).messenger(inbox_ref)` (`multi-inbox.md`) |
