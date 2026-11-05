# CLAUDE.md

## Project Overview

Wappa is an open source framework for developing smart workflows, agents, and full chat applications through WhatsApp.

## DDD and Architecture Grounding

Wappa is a Platform-facing messaging runtime. It should not define business tenancy for host applications.

Before non-trivial code, schema, architecture, public contract, or documentation changes:

1. Read root `CONTEXT.md` for Wappa's canonical language.
2. Read `CONTEXT-MAP.md` to locate the target context.
3. Read root `ARCHITECTURE.md` and the nearest context `ARCHITECTURE.md` for the folder being touched. Create or update architecture docs when a module responsibility, seam, adapter, interface, or folder rule changes.
4. Read relevant ADRs under `docs/adr/` and context-local `docs/adr/` when present.
5. Check `docs/public-contract.md` before changing any surface that host applications may import, call, configure, subscribe to, or depend on.

For architecture work, DDD naming, SOLID cleanup, or design discussion:

- Challenge ambiguous terms against `CONTEXT.md`.
- Prefer canonical Wappa terms already defined there.
- Cross-check claims against code before treating them as true.
- Ask one design question at a time when the answer cannot be discovered from code, and include the recommended answer.
- Update `CONTEXT.md` immediately when a domain term is resolved. Keep it a glossary only, not an implementation plan.
- Update `ARCHITECTURE.md` when a module responsibility, seam, adapter, interface, or folder rule changes.
- Create or update an ADR only when the decision is hard to reverse, surprising without context, and the result of a real trade-off.

### Canonical Wappa Runtime Language

- **Inbox**: the Platform-facing message ingress/egress identity used to receive webhooks, send messages, scope runtime caches, and subscribe to event streams.
- `inbox_id`: the stable Platform-native identifier of an Inbox. It is unique only inside one Platform; the globally unique identity is `InboxRef(platform, inbox_id)`. For WhatsApp, `inbox_id` maps to Meta `phone_number_id`.
- **Platform**: an external messaging platform such as WhatsApp. (Older instructions said "Provider"; Platform is canonical, matching `PlatformType`.)
- **Platform Account**: Platform-side account metadata such as WABA ID, identified globally by `PlatformAccountRef(platform, platform_account_id)`. This is not Wappa's runtime identity.
- **Inbox Routing Mode**: `legacy` (settings-backed single Inbox) or `explicit` (Wappa's encrypted Inbox Directory over the Host's `IInboxDirectorySource`). No third mode exists.
- **User**: the end-user/contact identity inside a Platform conversation.
- **Host Application**: the application embedding Wappa and owning business concepts such as Owner, Channel, customer, or workflow.

Avoid `tenant`, `tenant_id`, and `multi-tenant` as Wappa runtime language. Wappa may carry optional host metadata, but it does not define business tenancy, Owner, or Channel.

### Wappa Architectural Defaults

- Host applications own business language and business invariants.
- Wappa owns Platform webhook intake, message sending, event dispatch, runtime cache scoping, and public contract stability.
- API route modules adapt HTTP to Wappa modules; they should not own Platform parsing, credential lookup, cache namespace rules, or dispatch policy.
- Platform adapters own SDK/client construction, credentials, request/response translation, Platform errors, and Platform-specific identity mapping.
- Keep the WhatsApp `inbox_id == phone_number_id` mapping explicit inside the WhatsApp adapter.
- Cache, SSE, expiry, and event modules scope runtime data by Inbox identity where Platform-facing identity is required; only Table Cache accepts a general `context_id`.
- Prefer deep modules: keep interfaces small and place behavior behind them for leverage and locality.
- Avoid pass-through modules that fail the deletion test.
- Treat the public import surface, CLI templates, webhook routes, event envelopes, cache namespace shape, and generated examples as Wappa's public contract.

## Key Files and Components

### Core Framework Components

- **`wappa/__init__.py`**: Clean library interface, framework essentials only
- **`wappa/core/wappa_app.py`**: Main application factory with plugin system
- **`wappa/core/factory/wappa_builder.py`**: Builder pattern for complex applications
- **`wappa/core/events/event_dispatcher.py`**: Universal webhook dispatcher
- **`wappa/core/events/event_handler.py`**: Base event handler interface

### Messaging System

- **`wappa/domain/interfaces/messaging_interface.py`**: Platform-agnostic messaging contract
- **`wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`**: WhatsApp implementation
- **`wappa/messaging/whatsapp/client/whatsapp_client.py`**: WhatsApp Business API client
- **`wappa/messaging/whatsapp/handlers/`**: Message type handlers (media, interactive, templates)

### CLI System

- **`wappa/cli/main.py`**: Complete CLI with Typer integration
- **`wappa/cli/templates/`**: Project scaffolding templates
- **`wappa/cli/examples/`**: Example projects copied by `wappa examples`

### Persistence Layer

- **`wappa/persistence/`**: Multiple cache backends (Memory, JSON, Redis)
- **`wappa/persistence/cache_factory.py`**: Factory for cache backend selection

### Configuration & Plugins

- **`wappa/core/config/settings.py`**: Pydantic settings with environment support
- **`wappa/core/plugins/`**: Built-in plugins (Auth, CORS, Rate limiting, Redis, Database)
- **`wappa/core/logging/logger.py`**: Structured logging with context

## Important Implementation Details

### Basic Wappa Application Setup

```python
from wappa import Wappa, WappaEventHandler


class MasterEventHandler(WappaEventHandler):
    async def process_message(self, webhook):
        # Your business logic here. `self.messenger` is injected per request.
        await self.messenger.send_text(
            recipient=webhook.user.user_id,
            text="Hello!",
        )


# Minimal application setup (legacy single-Inbox mode). Credentials are
# read from the environment (.env): META_APP_SECRET, WP_WEBHOOK_VERIFY_TOKEN,
# WP_ACCESS_TOKEN, WP_PHONE_ID, WP_BID. The constructor selects the cache
# backend ("memory" | "redis" | "json") and, optionally, the Inbox Routing
# Mode plus an IInboxDirectorySource for explicit multi-Inbox routing.
app = Wappa(cache="memory")

# Register the event handler
app.set_event_handler(MasterEventHandler())

if __name__ == "__main__":
    app.run()
```

### Advanced Setup with Builder Pattern

For complex applications with plugins and custom configuration, use `WappaBuilder` directly. `build()` returns a configured FastAPI app (synchronous); wire it back into `Wappa` for event handling and running. Plugins are real classes imported from `wappa.core.plugins` and added via `add_plugin(...)`. WhatsApp credentials still come from the environment (.env: `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`).

```python
from wappa import Wappa, WappaBuilder
from wappa.core.plugins import (
    CORSPlugin,
    RateLimitPlugin,
    RateLimitProfile,
    RedisPlugin,
)

# Assemble the FastAPI app via the builder (build() is synchronous).
fastapi_app = (
    WappaBuilder()
    .add_plugin(RedisPlugin())            # Redis cache/session infrastructure
    .add_plugin(CORSPlugin(allow_origins=["*"]))
    .add_plugin(
        RateLimitPlugin(
            [RateLimitProfile(name="default", limit=100, window_seconds=60)]
        )
    )
    .configure(title="My Wappa App", version="2.0.0")
    .build()
)

# Use the Wappa class for event handling and running.
app = Wappa()
app.set_app(fastapi_app)
app.set_event_handler(MasterEventHandler())

if __name__ == "__main__":
    app.run()
```

Alternatively, for plugin extensibility without dropping to the builder, add plugins straight on the `Wappa` instance:

```python
from wappa import Wappa
from wappa.core.plugins import PostgresDatabasePlugin

app = Wappa(cache="redis")
app.add_plugin(PostgresDatabasePlugin("postgresql://..."))
app.set_event_handler(MasterEventHandler())
app.run()
```

## Development Guidelines

### Library Development

When extending the Wappa library:

1. **Maintain Clean Imports**: Keep `wappa/__init__.py` minimal - only framework essentials
2. **Plugin Architecture**: Use `WappaPlugin` for extensibility rather than modifying core
3. **Interface-Driven**: All external services behind abstract interfaces  
4. **Event Handler Pattern**: Business logic in custom `WappaEventHandler` subclasses

### Example Projects Maintenance

Keep examples updated with library changes and ensure they demonstrate best practices.

### Formatting

Use `ruff format` only. `black` is still a dev dependency, but its `[tool.black]` config (`skip-string-normalization`) disagrees with Ruff's double quotes, so running it churns the codebase.
