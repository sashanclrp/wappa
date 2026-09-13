# Migrating to the pluggable SSE hub

Wappa v0.29.0 exposes a public, broker-neutral SSE transport contract. Standard
applications using `SSEEventsPlugin()` need no change: they retain the default
in-memory hub and the established JSON event envelope.

## Replace private hub mutation

Do not replace `plugin._event_hub`, mutate lifecycle middleware, read a hub's
subscriber dictionary, or call private hub helpers. Provide the integration at
plugin construction instead:

```python
from wappa.core.plugins import SSEEventsPlugin
from wappa.sse import SSEHub

plugin = SSEEventsPlugin(
    event_hub_factory=lambda queue_size: BrokeredSSEHub(queue_size=queue_size)
)
```

Implement `SSEHub` structurally; inheriting from `SSEEventHub` is neither
required nor recommended. The factory runs once per Wappa application runtime.
Pass an already-created `event_hub=` only when its lifecycle is intentionally
bound to that one runtime. Supplying both raises `ValueError`.

## Broker decorator shape

`publish()` creates the one Wappa envelope. A decorator may send that exact
envelope to its broker after local publication. When the broker later yields an
envelope from another process, call `deliver_envelope(envelope)`; never call
`publish()` for that path because it would create a new event ID and rebroadcast
the remote delivery.

```python
result = await hub.publish(
    event_type="incoming_message", source="wappa", payload={"...": "..."}
)
await broker.publish(result.envelope.to_dict())

# In the broker consumer:
hub.deliver_envelope(received_envelope)
```

Use `snapshot_metrics()` for observability. It is process-local; broker metrics
belong under the `SSEHubMetrics.custom` mapping supplied by the custom hub.

## Slow clients

The old drop-oldest behavior has been removed. A full queue creates a Delivery
Gap and closes that client stream with `backpressure_gap`. EventSource reconnects
automatically; reconcile the client from durable Host state after reconnecting.
SSE has no replay guarantee and Wappa does not add a durable event ledger.
