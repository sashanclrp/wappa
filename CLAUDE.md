# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Wappa is an open source framework for developing smart workflows, agents, and full chat applications through WhatsApp. The project is currently in refactoring phase, transitioning from a monolithic application (`/app`) into a modular open source library with a CLI tool.

### Vision & Refactoring Goals

1. **Library Interface**: Enable `from wappa import WhatsAppMessenger` for clean messaging integration
2. **CLI Tool**: Create `wappa` command-line tool for project scaffolding (`uvx wappa init`, `uv run wappa init`)
3. **Core Focus**: WhatsApp webhooks + Messenger interface + event dispatcher (remove Airtable, payment services)
4. **Minimal Scaffolding**: Only webhooks → event dispatcher → event handlers (everything else imported from Wappa module)

## Development Commands

### CLI Commands (Post-Refactor)

```bash
# Install dependencies and sync project
uv sync

# Initialize new Wappa project
wappa init                     # Initialize in current directory  
wappa init my-bot             # Initialize in ./my-bot/ directory
uv run wappa init             # Alternative using uv run

# Copy example projects
wappa examples                # Interactive examples menu
wappa examples my-bot         # Copy example to ./my-bot/

# Development server
wappa dev main.py             # Run development server with auto-reload
wappa dev app/main.py --port 8080
uv run wappa dev app/main.py  # Alternative using uv run

# Production server  
wappa prod main.py            # Production server (no auto-reload)
wappa prod main.py --workers 4 --port 8080

# Code formatting and linting
uv run ruff check .           # Lint code
uv run ruff format .          # Format code
uv run black .                # Format with Black (alternative)

# Testing
uv run pytest                 # Run tests (when test suite exists)
uv run pytest tests/         # Run specific test directory

# Development dependencies
uv sync --group dev           # Install development dependencies
```

## Architecture Overview

### Current Architecture (Refactored)

The project has been successfully refactored into a modular library with clean architecture principles:

#### Core Framework Components

1. **Wappa Application** (`wappa/core/wappa_app.py`)
   - Main application factory with plugin system
   - Clean import: `from wappa import Wappa`
   - Built-in FastAPI integration with sensible defaults

2. **Event System** (`wappa/core/events/`)
   - Universal event dispatcher for all webhook types
   - Clean separation between webhook parsing and business logic
   - Plugin-based event handler registration

3. **Messaging Layer** (`wappa/messaging/whatsapp/`)
   - Complete WhatsApp Business API implementation
   - Platform-agnostic messaging interfaces
   - Handlers for all message types: text, media, interactive, templates, specialized

4. **CLI Tools** (`wappa/cli/`)
   - `wappa init` - project scaffolding
   - `wappa dev/prod` - development/production servers  
   - `wappa examples` - interactive example browser with 6 templates

#### Key Architecture Patterns

- **Plugin Architecture**: Extensible through `WappaBuilder` and `WappaPlugin`
- **Clean Imports**: Framework essentials exposed at top level (`from wappa import Wappa`)
- **Domain Separation**: Business logic separate from framework concerns
- **Factory Pattern**: `WappaBuilder` for complex application assembly
- **Interface-Driven Design**: Abstract interfaces for messaging, caching, persistence

## DDD and Architecture Grounding

Wappa is a provider-facing messaging runtime. It should not define business tenancy for host applications.

Before non-trivial code, schema, architecture, public contract, or documentation changes:

1. Read root `CONTEXT.md` for Wappa's canonical language. If it does not exist yet, create it as part of the first terminology-changing task.
2. Read `CONTEXT-MAP.md` if present. If absent, treat Wappa as a single-context repo until a real second context exists.
3. Read root `ARCHITECTURE.md` and the nearest context `ARCHITECTURE.md` for the folder being touched. Create or update architecture docs when a module responsibility, seam, adapter, interface, or folder rule changes.
4. Read relevant ADRs under `docs/adr/` and context-local `docs/adr/` when present.
5. Check `docs/public-contract.md` before changing any surface that host applications may import, call, configure, subscribe to, or depend on. If no public-contract doc exists and the change affects the public interface, create it or update the nearest public-contract documentation.

For architecture work, DDD naming, SOLID cleanup, or design discussion:

- Challenge ambiguous terms against `CONTEXT.md`.
- Prefer canonical Wappa terms already defined there.
- Cross-check claims against code before treating them as true.
- Ask one design question at a time when the answer cannot be discovered from code, and include the recommended answer.
- Update `CONTEXT.md` immediately when a domain term is resolved. Keep it a glossary only, not an implementation plan.
- Update `ARCHITECTURE.md` when a module responsibility, seam, adapter, interface, or folder rule changes.
- Create or update an ADR only when the decision is hard to reverse, surprising without context, and the result of a real trade-off.

### Canonical Wappa Runtime Language

- **Inbox**: the provider-facing message ingress/egress identity used to receive webhooks, send messages, scope runtime caches, and subscribe to event streams.
- `inbox_id`: the stable identifier of an Inbox inside Wappa. For WhatsApp, this maps to Meta `phone_number_id`.
- **Provider**: an external messaging platform such as WhatsApp.
- **Provider Account**: provider-side account metadata such as WABA ID. This is not Wappa's runtime identity.
- **User**: the end-user/contact identity inside a provider conversation.
- **Host Application**: the application embedding Wappa and owning business concepts such as Owner, Channel, customer, or workflow.

Avoid `tenant`, `tenant_id`, and `multi-tenant` as Wappa runtime language. Wappa may carry optional host metadata, but it does not define business tenancy, Owner, or Channel.

### Wappa Architectural Defaults

- Host applications own business language and business invariants.
- Wappa owns provider webhook intake, message sending, event dispatch, runtime cache scoping, and public contract stability.
- API route modules adapt HTTP to Wappa modules; they should not own provider parsing, credential lookup, cache namespace rules, or dispatch policy.
- Provider adapters own SDK/client construction, credentials, request/response translation, provider errors, and provider-specific identity mapping.
- Keep the WhatsApp `inbox_id == phone_number_id` mapping explicit inside the WhatsApp adapter.
- Cache, SSE, expiry, and event modules scope runtime data by `inbox_id` where provider-facing identity is required.
- Prefer deep modules: keep interfaces small and place behavior behind them for leverage and locality.
- Avoid pass-through modules that fail the deletion test.
- Treat the public import surface, CLI templates, webhook routes, event envelopes, cache namespace shape, and generated examples as Wappa's public contract.

### Library Structure

The refactored library provides:

1. **Simple Import**: `from wappa import Wappa, WappaEventHandler`
2. **Plugin System**: Extensible through `WappaBuilder` and plugins
3. **CLI Scaffolding**: `wappa init` creates minimal project structure  
4. **Multiple Cache Backends**: Memory, JSON file, Redis support
5. **Rich Examples**: 6 example templates from basic to full-featured

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
- **`wappa/cli/examples/`**: 6 example projects (basic to full-featured)

### Persistence Layer

- **`wappa/persistence/`**: Multiple cache backends (Memory, JSON, Redis)
- **`wappa/persistence/cache_factory.py`**: Factory for cache backend selection
- **`wappa/database/adapters/`**: Database adapters (SQLite, PostgreSQL, MySQL)

### Configuration & Plugins

- **`wappa/core/config/settings.py`**: Pydantic settings with environment support
- **`wappa/core/plugins/`**: Built-in plugins (Auth, CORS, Rate limiting, Redis, Database)
- **`wappa/core/logging/logger.py`**: Structured logging with context

## Important Implementation Details

### Basic Wappa Application Setup

The refactored library provides clean, minimal setup:

```python
from wappa import Wappa, WappaEventHandler


class MasterEventHandler(WappaEventHandler):
    async def handle_message(self, webhook):
        # Your business logic here. `self.messenger` is injected per request.
        await self.messenger.send_text(
            recipient=webhook.user.user_id,
            text="Hello!",
        )


# Minimal application setup. Credentials are read from the environment
# (.env): WP_ACCESS_TOKEN, WP_PHONE_ID, WP_BID. The constructor only
# selects the cache backend ("memory" | "redis" | "json").
app = Wappa(cache="memory")

# Register the event handler
app.set_event_handler(MasterEventHandler())

if __name__ == "__main__":
    app.run()
```

### Advanced Setup with Builder Pattern

For complex applications with plugins and custom configuration, use
`WappaBuilder` directly. `build()` returns a configured FastAPI app
(synchronous); wire it back into `Wappa` for event handling and running.
Plugins are real classes imported from `wappa.core.plugins` and added via
`add_plugin(...)`. WhatsApp credentials still come from the environment
(.env: `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`).

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

Alternatively, for plugin extensibility without dropping to the builder,
add plugins straight on the `Wappa` instance:

```python
from wappa import Wappa
from wappa.core.plugins import PostgresDatabasePlugin

app = Wappa(cache="redis")
app.add_plugin(PostgresDatabasePlugin("postgresql://..."))
app.set_event_handler(MasterEventHandler())
app.run()
```

### CLI Project Scaffolding

The CLI creates minimal project structure:

```bash
wappa init my-bot
# Creates:
# my-bot/
#   app/
#     __init__.py
#     main.py          # Wappa app instance (Wappa() + set_event_handler)
#     master_event.py  # Event handler (WappaEventHandler subclass)
#     scores/          # Empty package for business logic
#       __init__.py
#   .env               # Environment variables template (WP_* credentials)
#   .gitignore         # Git ignore file
```

### Example Projects Available

6 example templates available via `wappa examples`:

1. **Basic Project** - Minimal setup with message handling
2. **Simple Echo Bot** - Message echoing with media support
3. **JSON Cache Demo** - File-based caching with user management
4. **Redis Cache Demo** - Redis caching with advanced state management
5. **OpenAI Transcription** - Voice message transcription
6. **Full-Featured Bot** - Complete bot with all features and Docker deployment

## Development Guidelines

### Library Development

When extending the Wappa library:

1. **Maintain Clean Imports**: Keep `wappa/__init__.py` minimal - only framework essentials
2. **Plugin Architecture**: Use `WappaPlugin` for extensibility rather than modifying core
3. **Interface-Driven**: All external services behind abstract interfaces  
4. **Event Handler Pattern**: Business logic in custom `WappaEventHandler` subclasses
5. **Builder Pattern**: Use `WappaBuilder` for complex application assembly

### Core Components (Stable)
- Messaging interfaces and WhatsApp implementation
- Event dispatcher and universal webhook parsing
- Plugin system and factory patterns
- CLI tools and project scaffolding
- Multiple cache backends (Memory, JSON, Redis)
- Database adapters and configuration management

### Example Projects Maintenance

The 6 example projects serve as:
- **Documentation**: Working code examples
- **Testing**: Integration tests for various features
- **Scaffolding**: Quick-start templates for users

Keep examples updated with library changes and ensure they demonstrate best practices.

## Development Notes

- **Python 3.12**: Target Python version with modern type hints and features
- **uv Package Manager**: Primary dependency management (prefer over pip/poetry)
- **FastAPI**: Web framework with async support and automatic OpenAPI docs  
- **Typer**: CLI framework with Rich integration for beautiful terminal UI
- **Ruff**: Primary linter and formatter (preferred over Black/flake8)
- **Pydantic**: Settings and data validation with v2 features
- **Plugin Architecture**: Extensible design through `WappaBuilder` and `WappaPlugin`

### Key Technical Decisions

- **Clean Imports**: `from wappa import Wappa` - library interface follows SRP
- **Universal Webhooks**: Platform-agnostic webhook parsing with specialized handlers
- **Multi-Backend Persistence**: Memory, JSON file, and Redis cache implementations
- **CLI-First Experience**: Rich terminal UI with interactive examples browser
- **Docker Ready**: Examples include production deployment configurations

The refactored library demonstrates mature software engineering practices with clean architecture, extensive plugin system, and comprehensive CLI tooling.
