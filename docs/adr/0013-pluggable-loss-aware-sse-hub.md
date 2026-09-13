# ADR-0013: Pluggable, loss-aware SSE hub

## Status

Accepted on 2026-09-13.

## Decision

Wappa's SSE integration depends on the public structural `SSEHub` contract,
not `SSEEventHub`. `SSEEventsPlugin` creates one injected hub per application
runtime and gives the same object to routes, wrappers, Messenger middleware,
lifecycle, and health. `publish()` creates a typed envelope, while
`deliver_envelope()` performs local-only fan-out of an existing envelope so a
Host broker adapter never rebroadcasts remote work.

The default in-memory hub closes a Subscription on its first queue overflow.
It records a Delivery Gap and a private close control rather than silently
drops an event while leaving the stream active. SSE stays process-local and
non-durable; reconciliation belongs to the Host.

## Why

Cross-process delivery needs a supported adapter seam, but broker technology,
business subjects, users, and notification semantics belong to Host applications.
Continuing after an unknown queue loss makes a connected client appear current
when it is not. Closing and reconnecting makes the loss observable without
claiming replay or durability Wappa cannot provide.
