# Coding Standards

Standards an agent needs once a task reaches code, tests, commits, examples, or design discussion. `AGENTS.md` points here; `CONTRIBUTING.md` carries the human-facing version and the detailed code and test conventions.

## Check gates

Install with `uv sync --group dev`. All four checks pass before every commit:

```bash
uv run ruff check .
uv run ruff format .
uv run mypy wappa
uv run pytest -q
```

## Formatting

Format with `ruff format`; Ruff is the only linter and formatter. `black` is still a dev dependency, but its `[tool.black]` config (`skip-string-normalization`) disagrees with Ruff's double quotes, so running it churns the codebase.

## Code and test conventions

Follow the "Code conventions" and "Tests" sections of `CONTRIBUTING.md`: strict mypy typing, Python 3.12 built-in generics, offline tests with fakes, one parameterized suite per multi-backend contract, and a regression test that fails before every fix.

## Commits

- Format: `[ACTION] [SCOPE] Short description`.
- Scope each commit to one Wappa area: runtime, Platform adapter, API contract, persistence, CLI/templates, docs, or tests.
- Leave generated or local-only artifacts untracked and visible in `git status`; `git add` them only when the task explicitly asks to commit generated artifacts.

Examples:

- `[MOD] [CONTRACT] Rename webhook runtime identity to inbox_id`
- `[MOD] [WHATSAPP] Map inbox_id to Meta phone_number_id`
- `[ADD] [ADR] Record Inbox as Wappa runtime scope`

## Design discussions and documentation upkeep

For architecture work, refactoring, DDD, domain naming, SOLID cleanup, or a design discussion, follow the `grill-with-docs` discipline:

- Challenge ambiguous or conflicting terms against `CONTEXT.md` and prefer the canonical Wappa terms defined there.
- Cross-check claims against code before treating them as true.
- Ask one design question at a time when the codebase cannot answer it, and include the recommended answer.
- Update `CONTEXT.md` immediately when a domain term is resolved. Keep it a glossary of definitions; implementation plans go in `docs/implementation-plans/`.
- Update `ARCHITECTURE.md` when a module responsibility, seam, adapter, interface, or folder rule changes.
- Create or update an ADR only when the decision is hard to reverse, surprising without context, and the result of a real trade-off.

## Extending the library

- Keep `wappa/__init__.py` to framework essentials; everything else is imported from its subpackage.
- Extend through `WappaPlugin` and leave the core untouched.
- Put every external service behind an abstract interface.
- Host business logic lives in `WappaEventHandler` subclasses.

Where the main pieces live:

- `wappa/__init__.py`: public import surface.
- `wappa/core/wappa_app.py`: `Wappa` application factory and plugin hookup.
- `wappa/core/factory/wappa_builder.py`: `WappaBuilder` for complex assembly.
- `wappa/core/events/event_dispatcher.py`: universal webhook dispatcher.
- `wappa/core/events/event_handler.py`: `WappaEventHandler` base interface.
- `wappa/domain/interfaces/messaging_interface.py`: Platform-agnostic messaging contract.
- `wappa/messaging/whatsapp/messenger/whatsapp_messenger.py`, `wappa/messaging/whatsapp/client/whatsapp_client.py`, `wappa/messaging/whatsapp/handlers/`: WhatsApp messenger, Business API client, and per-message-type handlers.
- `wappa/cli/main.py`, `wappa/cli/templates/`, `wappa/cli/examples/`: Typer CLI, `wappa init` scaffolding templates, and projects copied by `wappa examples`.
- `wappa/persistence/` and `wappa/persistence/cache_factory.py`: Memory, JSON, and Redis cache backends and backend selection.
- `wappa/core/config/settings.py`: Pydantic settings from the environment.
- `wappa/core/plugins/`: built-in plugins (Auth, CORS, Rate limiting, Redis, Database).
- `wappa/core/logging/logger.py`: structured logging with context.

## Example apps and templates

Examples in `wappa/cli/examples/` and templates in `wappa/cli/templates/` are public contract: update them in the same change as the library API they use, and keep them demonstrating current best practice.

Runtime configuration comes from the environment; `.env.example` documents it. Every mode needs `META_APP_SECRET` and `WP_WEBHOOK_VERIFY_TOKEN`. Legacy mode adds `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`; explicit mode uses `SYSTEM_TOKEN_ENC_KEY` instead of the `WP_*` bundle.

Minimal application (legacy single-Inbox mode). The constructor selects the cache backend (`"memory"`, `"redis"`, `"json"`) and, optionally, the Inbox Routing Mode plus an `IInboxDirectorySource` for explicit multi-Inbox routing:

```python
from wappa import Wappa, WappaEventHandler


class MasterEventHandler(WappaEventHandler):
    async def process_message(self, webhook):
        # `self.messenger` is injected per request.
        await self.messenger.send_text(
            recipient=webhook.user.user_id,
            text="Hello!",
        )


app = Wappa(cache="memory")
app.set_event_handler(MasterEventHandler())

if __name__ == "__main__":
    app.run()
```

Builder assembly for plugins and custom configuration. `WappaBuilder.build()` is synchronous and returns a configured FastAPI app; wire it back into `Wappa` with `set_app` for event handling and running. Plugins are classes from `wappa.core.plugins`:

```python
from wappa import Wappa, WappaBuilder
from wappa.core.plugins import (
    CORSPlugin,
    RateLimitPlugin,
    RateLimitProfile,
    RedisPlugin,
)

fastapi_app = (
    WappaBuilder()
    .add_plugin(RedisPlugin())
    .add_plugin(CORSPlugin(allow_origins=["*"]))
    .add_plugin(
        RateLimitPlugin(
            [RateLimitProfile(name="default", limit=100, window_seconds=60)]
        )
    )
    .configure(title="My Wappa App", version="2.0.0")
    .build()
)

app = Wappa()
app.set_app(fastapi_app)
app.set_event_handler(MasterEventHandler())

if __name__ == "__main__":
    app.run()
```

Plugins without the builder, added straight on the `Wappa` instance:

```python
from wappa import Wappa
from wappa.core.plugins import PostgresDatabasePlugin

app = Wappa(cache="redis")
app.add_plugin(PostgresDatabasePlugin("postgresql://..."))
app.set_event_handler(MasterEventHandler())
app.run()
```
