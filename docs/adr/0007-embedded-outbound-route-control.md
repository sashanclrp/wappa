# ADR-0007: Embedded Outbound Route Control

**Status:** Accepted  
**Date:** 2026-08-05  
**Extends:** ADR-0006

## Context

`create_whatsapp_router()` mounted Wappa's ordinary outbound mutation routes —
send-text, media sends, interactive sends, contact and location sends,
mark-as-read — in the same call that mounts media upload/download/lookup,
limits, validation, Template info, state handlers, and health.

An embedding Host Application that owns an authenticated Operator boundary
cannot accept the first group: those routes send to real Users with only Wappa's
own inbox credentials behind them, bypassing the host's authorization entirely.
But it still needs the second group, and the two share URL prefixes
(`/media/upload` next to `/media/send-image`), so "drop the router" is not an
option. Copying or monkeypatching Wappa's routers is the workaround this ADR
exists to remove.

ADR-0006 already made Template mutations opt-in and off by default. Applying
the same default to ordinary outbound routes would delete the HTTP surface that
every standalone Wappa application, example project, and README snippet uses
today.

## Decision

Split each mixed route module into two routers built from one description —
an outbound-mutation router and a service router — and let
`create_whatsapp_router()` choose them independently:

```python
create_whatsapp_router(
    include_outbound_transport=True,   # default: standalone behavior preserved
    include_template_transport=False,  # default: ADR-0006, unchanged
)
```

`Wappa(include_outbound_transport_api=False)` is the embedding host's switch.
Turning it off removes every ordinary and interactive outbound mutation route
and nothing else.

The two defaults are deliberately asymmetric:

- **Template mutations default to off** because they were introduced as an
  opt-in capability. Nothing depended on them being mounted.
- **Ordinary mutations default to on** because they are the documented
  standalone HTTP surface. Flipping that default would be a silent breaking
  change for every existing deployment, and the safety win would be zero for
  the hosts that already have to pass a flag either way.

`wappa.messaging` services — `IMessenger`, `OutboundRuntime`,
`InboxTemplateTransport` — are unaffected by route composition. Omitting the
HTTP surface never removes the ability to send; it removes the *unauthenticated*
ability to send.

## Consequences

- An embedding host upgrades by passing one constructor argument, with no
  router copying, path filtering, or middleware-based blocking.
- Standalone Wappa applications see no change without asking for one.
- The outbound/service line now lives in the route modules themselves, so a new
  send endpoint added to a service router is visible in review as a router name
  that does not match what the route does.
- Route-composition tests assert against the generated route table rather than
  the constructor flags, because the guarantee is about which URLs exist.
