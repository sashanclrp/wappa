# WappaFlex: Wappa + Reflex Integration Analysis

> **Date**: 2026-03-07
> **Status**: Research & Design Phase
> **Decision**: Documented trade-offs — no implementation started

---

## Context

Reflex is a Python full-stack framework that compiles to React, uses FastAPI internally, communicates via WebSocket, and manages per-user state on the server with optional Redis persistence. The question: how should Wappa (WhatsApp webhook framework) integrate with Reflex?

---

## Three Options Evaluated

### Option A: Wappa inside Reflex (via `api_transformer`)

Mount Wappa's FastAPI app into Reflex using Reflex's `api_transformer` parameter.

```python
app = rx.App(api_transformer=wappa.asgi)
```

- Reflex owns the ASGI lifecycle, Wappa runs as a sub-app
- Webhook routes (`/webhook/messenger/...`) become available on the same server
- Requires a **Redis pub/sub bridge** to push WhatsApp events into `rx.State`
- `WappaEventHandler` protocol stays intact

**Verdict**: Works but requires a bridge layer. Two-hop latency for events.

### Option B: Wappa backend + Vite frontend (recommended for chat UI)

Keep Wappa as a standalone FastAPI backend. Build the chat UI with Vite (React/Vue).

```
Vite SPA <──SSE/WS──> Wappa Backend <──Webhooks──> WhatsApp
```

- Wappa already ships SSEEventsPlugin, CORS plugin, REST API routes
- Direct SSE connection from browser to Wappa — no bridge needed
- Full control over chat UI with React/Vue + any UI library
- Standard frontend dev — massive ecosystem, no Python abstractions fighting you

**Verdict**: Easiest path. Zero glue code. Best for real-time chat interfaces.

### Option C: WappaFlex — Native Reflex integration (this document)

Build a dedicated integration layer so Wappa events natively update Reflex UI.

**Verdict**: Buildable (~1500-2000 lines) but adds complexity. Makes sense only if the team is Python-only and accepts trade-offs.

---

## WappaFlex Architecture (Option C Detail)

### The Core Problem

Wappa and Reflex live in two different event worlds:

| Aspect | Wappa | Reflex |
|--------|-------|--------|
| Event source | WhatsApp webhooks (HTTP POST from Meta) | Browser interactions (WebSocket from user) |
| State model | Stateless per-request (clone pattern) | Stateful per-session (`rx.State`) |
| Who triggers | External (WhatsApp Cloud API) | Internal (user clicks/types) |
| Push mechanism | SSE / Redis PubSub | WebSocket (automatic on state change) |

A WhatsApp webhook arrives with **zero browser session context**. You cannot directly mutate `rx.State` from a webhook handler. Redis pub/sub bridges the gap.

### 4-Layer Architecture

```
+-----------------------------------------------------------+
|  LAYER 4: Reflex UI Components                            |
|  WappaChatBox, WappaMessageList, WappaSendBar, etc.       |
|  Pure rx.Component - renders from WappaFlexState           |
+-----------------------------------------------------------+
|  LAYER 3: WappaFlexState (rx.SharedState)                 |
|  Reactive state shared across all admin users              |
|  Background task subscribes to Redis channel               |
|  Event handlers for sending messages from UI               |
+-----------------------------------------------------------+
|  LAYER 2: WappaFlexBridge (WappaEventHandler subclass)    |
|  Publishes all events to Redis pub/sub + sorted sets       |
|  Replaces SSE as the frontend delivery mechanism           |
+-----------------------------------------------------------+
|  LAYER 1: Wappa Core (unchanged)                          |
|  Webhook routes, WhatsApp client, messenger, dispatcher    |
|  Mounted via api_transformer into Reflex                   |
+-----------------------------------------------------------+
```

### Layer 1: Wappa Core (unchanged)

Mounted into Reflex via `api_transformer`:

```python
wappa = Wappa(cache="redis")
wappa.register_handler(WappaFlexBridge())
app = rx.App(api_transformer=wappa.asgi)
```

**Compatibility concerns:**
- `.asgi` must return FastAPI app without calling `uvicorn.run()`
- Webhook routes must not collide with Reflex's `/_reflex/` and `/api/` paths
- Lifespan hooks (startup/shutdown) must fire under Reflex's ASGI management

### Layer 2: WappaFlexBridge

A custom `WappaEventHandler` subclass that publishes to Redis instead of SSE.

**Key methods:**
- `process_message(webhook)` — Incoming WhatsApp message: persist to Redis sorted set + publish to channel
- `process_status(webhook)` — Delivery/read status: publish to channel
- `process_api_message(event)` — Outgoing messages sent via API: persist + publish
- Bot replies still use `self.messenger` normally

**Redis data model:**
- **Sorted sets** for chat history: `wappaflex:messages:{tenant}:{user_id}` (scored by timestamp)
- **Pub/sub channel** for real-time events: `wappaflex:events`
- **Event schema**: `{type, tenant_id, user_id, sender_phone, content, message_id, timestamp, status}`

**Why the clone pattern still works:**
- `WappaFlexBridge` is registered as the prototype handler
- Per-request cloning via `with_context()` injects tenant_id, user_id, messenger, cache_factory
- The bridge simply adds Redis publishing on top of normal handler behavior
- No changes to Wappa's dispatcher, controller, or middleware

### Layer 3: WappaFlexState

An `rx.SharedState` subclass with a background Redis subscriber.

**Key features:**
- `listen_for_events()` — `@rx.event(background=True)` that subscribes to `wappaflex:events` Redis channel. Inside `async with self:` blocks it mutates state, which automatically triggers WebSocket pushes to all connected browsers.
- `send_message(form_data)` — Called from UI form submit. Calls Wappa's REST API to send the WhatsApp message. The bridge's `process_api_message` publishes back to Redis, which the listener picks up.
- `load_chat(user_id)` — Loads history from Redis sorted set when user selects a conversation.

**Why `rx.SharedState`:**
- Multiple admin users can view the same WhatsApp conversations
- State changes propagate to ALL connected sessions via `_link_to`
- Each browser tab runs its own background subscriber (Redis pub/sub handles fan-out)

### Layer 4: Reflex UI Components

Standard Reflex components rendering from `WappaFlexState`:
- Conversation list sidebar (rx.foreach over conversations)
- Message bubbles (incoming vs outgoing styling)
- Send message form
- Status indicators (sent/delivered/read)

---

## Event Flow Diagrams

### Incoming WhatsApp Message

```
WhatsApp Cloud API
  |
  | HTTP POST (webhook)
  v
Wappa Webhook Route (Layer 1, via api_transformer)
  |
  | WebhookController clones handler with_context()
  v
WappaFlexBridge.process_message() (Layer 2)
  |
  | 1. ZADD to sorted set (persist)
  | 2. PUBLISH to channel (real-time)
  | 3. self.messenger.send_text() (reply on WhatsApp)
  v
Redis
  |
  | pub/sub message
  v
WappaFlexState.listen_for_events() (Layer 3, background task)
  |
  | async with self: self.messages.append(event)
  v
Reflex WebSocket (automatic)
  |
  | State change pushed to browser
  v
Chat UI re-renders (Layer 4)
```

### Outgoing Message from UI

```
Admin types message in Reflex UI (Layer 4)
  |
  | on_submit → WappaFlexState.send_message()
  v
WappaFlexState (Layer 3)
  |
  | HTTP POST to Wappa's /api/whatsapp/messages/text
  v
Wappa API Route (Layer 1)
  |
  | Sends via WhatsApp Cloud API
  | APIEventDispatcher calls handler.process_api_message()
  v
WappaFlexBridge.process_api_message() (Layer 2)
  |
  | 1. ZADD to sorted set (persist)
  | 2. PUBLISH to channel (real-time)
  v
Redis → WappaFlexState listener → WebSocket → UI re-renders
```

---

## Known Hard Problems

### 1. `rx.SharedState` Maturity

`rx.SharedState` with `_link_to` is relatively new in Reflex. Multi-user real-time chat pushes it hard. Must test:
- Concurrent state mutations from multiple subscribers
- Reconnection behavior after network drops
- Memory usage with many active conversations

### 2. Background Task Lifecycle

Each browser tab spawns its own `listen_for_events()` background task, each creating a Redis subscriber. Concerns:
- Redis connection pool exhaustion with many tabs
- Task survival across page navigation
- Graceful cleanup on disconnect

### 3. Message Ordering & Deduplication

WhatsApp can send duplicate webhooks. The Redis sorted set handles ordering by timestamp, but:
- Need dedup logic by `message_id` before appending to state
- Sorted set scores (timestamps) may collide — use `message_id` in the member value

### 4. Rendering Performance

`rx.foreach` over a growing messages list re-renders the entire list on every new message. For 1000+ messages:
- Reflex has no native list virtualization
- Pagination or windowing must be implemented manually
- This is a significant UX limitation vs. a React chat component

### 5. Two-Hop Latency

```
WhatsApp → Wappa → Redis → Reflex background task → WebSocket → browser
```

Compare with Wappa + Vite:
```
WhatsApp → Wappa → SSE → browser
```

Extra hop adds ~5-50ms depending on Redis and background task polling interval.

### 6. Sending Messages: HTTP Round-Trip

The Reflex UI sends messages by calling Wappa's REST API via `httpx`. This means:
- The Reflex process makes an HTTP call to itself (localhost)
- The message goes through Wappa's full middleware stack
- Then publishes back to Redis for the UI to pick up

An alternative is importing `MessengerFactory` directly and calling the messenger from within `rx.State`, but this breaks the WappaEventHandler protocol (no `process_api_message` gets called).

---

## Effort Estimate

| Component | Lines | Effort | Notes |
|-----------|-------|--------|-------|
| WappaFlexBridge | ~150 | Medium | WappaEventHandler subclass + Redis publishing |
| Redis event schema | ~50 | Low | Pydantic models for event types |
| WappaFlexState | ~300 | Medium-High | SharedState + background subscriber + send logic |
| Wappa `.asgi` compat | ~20 | Low | Verify lifespan and route namespacing |
| UI Components | 500-800 | High | Chat bubbles, sidebar, media, status indicators |
| Auth layer | ~200 | Medium | Admin user ↔ tenant/conversation mapping |
| Media handling | ~200 | Medium | Download + render WhatsApp media in Reflex |
| **Total** | **~1500-2000** | | |

---

## Comparison Summary

| Factor | Wappa + Vite | WappaFlex (Wappa + Reflex) |
|--------|-------------|---------------------------|
| New code needed | ~200 lines (fetch + render) | ~1500-2000 lines |
| Bridge layer | None (SSE direct) | Redis pub/sub bridge |
| Real-time latency | 1 hop (SSE) | 2 hops (Redis + background task) |
| Chat UI quality | Full React ecosystem | Limited by Reflex components |
| Media rendering | Native HTML5 | Must work around Reflex abstractions |
| List virtualization | react-virtualized etc. | Not available natively |
| Team requirement | Python + JS/TS | Python only |
| Debugging | Browser DevTools + SSE inspector | Reflex state inspector + Redis monitor |
| Deployment | 2 services (or static + API) | 1 service |

---

## Recommendation

- **For a chat-first application**: Use **Wappa + Vite** (Option B). The chat UI benefits enormously from direct SSE, React component ecosystem, and fine-grained rendering control.

- **For an admin dashboard with chat as a secondary feature**: **WappaFlex** (Option C) is viable. If the primary UI is forms, tables, dashboards, and analytics — and chat is one panel among many — Reflex's Python-only approach reduces context switching.

- **For prototyping**: WappaFlex is faster to prototype since it's all Python. But be aware of rendering limitations before committing to production.

---

## Reflex Key Concepts Reference

### `api_transformer`

Accepts a FastAPI/Starlette instance or callable. Reflex mounts its internal API onto the provided app:

```python
app = rx.App(api_transformer=my_fastapi_app)
```

### `rx.SharedState`

State shared across multiple browser sessions via `_link_to(token)`:

```python
class SharedRoom(rx.SharedState):
    messages: list[dict] = []

    @rx.event
    async def join(self, room_id: str):
        await self._link_to(f"room-{room_id}")
```

### Background Tasks

Long-running async tasks that can mutate state inside `async with self:` blocks:

```python
@rx.event(background=True)
async def listen(self):
    while True:
        data = await some_subscription()
        async with self:
            self.messages.append(data)  # triggers UI re-render
```

### State Mutation Rules

- State vars can only be modified inside event handlers or `async with self:` blocks
- External code (like webhook handlers) cannot directly modify `rx.State`
- This is WHY the Redis bridge is necessary

---

## Open Questions

1. **Does `api_transformer` properly delegate lifespan events?** Wappa's plugins register startup/shutdown hooks — these must fire.
2. **Can `rx.SharedState._link_to` handle 50+ concurrent users in a room?** No public benchmarks found.
3. **Should WappaFlexBridge extend or replace the SSE plugin?** If running WappaFlex, the SSE plugin is redundant — Redis pub/sub replaces it.
4. **Is there a way to push events into `rx.State` without Redis?** Reflex has no public API for external event injection. Redis is the cleanest bridge.
5. **Multi-tenant isolation in SharedState?** Each tenant's conversations should be a separate "room" via `_link_to(f"tenant-{tenant_id}")`.
