# CLI Context — Architecture

## Responsibilities

- Expose the `wappa` console script entry point via Typer.
- Scaffold a minimal Host Application directory (`wappa init`).
- Copy self-contained example projects to a target directory (`wappa examples`).
- Launch the ASGI server process for development (`wappa dev`) and production (`wappa prod`).

## Explicit Non-Responsibilities

- Does not parse webhooks or dispatch events.
- Does not own `inbox_id` identity or any runtime state.
- Does not configure WhatsApp credentials — only emits the required variable names into `.env`.
- Does not validate WhatsApp tokens or network connectivity.
- Does not generate or modify example projects at runtime — examples are static directories checked into source.

## Module Structure

```
wappa/cli/
  main.py              # The Typer app and thin commands (dev, prod, init, examples, migrate)
  scaffold.py          # `wappa init`: templates, shipped skills, safe-file allowlist
  serve.py             # dev/prod: ASGI server command building and launch
  examples_catalog.py  # `wappa examples`: the catalog, menu and copy
  templates/           # Static files rendered verbatim by `wappa init`
    __init__.py.template
    main.py.template
    master_event.py.template
    env.template
    gitignore.template
  examples/            # Self-contained runnable Host Application projects
    init/                     # Basic Project (Beginner)
    simple_echo_example/      # Simple Echo Bot (Beginner)
    wappa_expiry_example/     # Expiry Triggers Demo (Intermediate)
    scheduled_tasks_example/  # Scheduled Tasks Demo (Intermediate)
    json_cache_example/       # JSON Cache Demo (Intermediate)
    redis_cache_example/      # Redis Cache Demo (Intermediate)
    openai_transcript/        # OpenAI Transcription (Intermediate)
    redis_pubsub_example/     # Redis PubSub Plugin (Intermediate)
    db_redis_echo_example/    # DB + Redis Cache (Advanced)
    wappa_full_example/       # Full-Featured Bot (Advanced)
```

`main.py` holds only the Typer app and thin commands; each concern has its module beside it.

## Commands

| Command | What it does |
|---|---|
| `wappa init [directory]` | Creates `app/`, `app/scores/`, and renders all five templates into the target directory. Aborts if non-safe files already exist unless the user confirms. |
| `wappa examples [directory]` | Displays a Rich table of available examples, prompts for a selection, then copies the chosen example directory (excluding `__pycache__`, `.git`) into the target directory. |
| `wappa dev <file>` | Resolves the file to a Python import string, then spawns `uvicorn` (or `hypercorn`) with `--reload`. Single worker. |
| `wappa prod <file>` | Same resolution, spawns the ASGI server without `--reload`, with configurable `--workers`. |

Both `dev` and `prod` construct the import string as `<module>:<app_var>.asgi` where `app_var` defaults to `app`.

## Scaffolding Flow (`wappa init`)

1. Resolve the target path. Create the directory if it does not exist.
2. List existing files, excluding `pyproject.toml`, `uv.lock`, `README.md`. Prompt to continue if any are found.
3. Create `app/` and `app/scores/` directories.
4. Read each template from `cli/templates/` and write it to the corresponding output path.
5. Emit the shipped developer skills (`_emit_skills`, see below) without overwriting existing skill folders.
6. Print next-step instructions listing the required environment variables — the Meta Application Configuration (`META_APP_SECRET`, `WP_WEBHOOK_VERIFY_TOKEN`) and the legacy single-Inbox bundle (`WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`) — plus the one canonical callback URL, `/webhook/inboxes/whatsapp`.

The scaffolded `app/main.py` imports `Wappa` and calls `app.set_event_handler(MasterEventHandler())`. The Host Application fills in `MasterEventHandler` with business logic.

## Design Patterns

- **Thin command module**: commands live in `main.py`, their work in `scaffold.py`, `serve.py` and `examples_catalog.py`.
- **Static templates**: scaffolding reads raw text files from `cli/templates/`; no templating engine or variable substitution.
- **Static examples**: examples are complete directories committed to source. `wappa examples` is a file-copy operation, not code generation.
- **Subprocess delegation**: `dev` and `prod` spawn the ASGI server as a subprocess via `subprocess.run`, keeping the CLI process thin and server-agnostic.
- **Safe-file allowlist**: a frozen set (`_SAFE_EXISTING_FILES` in `scaffold.py`) guards non-empty directory detection without blocking valid project roots.

## Explicit targets in generated handlers

Generated scaffolds and bundled consumer examples construct `DirectMessage` with the Messenger's Platform/Inbox and a native recipient address. They do not send bare recipient strings to `IMessenger`. Examples never build or look up a capability: WhatsApp Templates are `self.whatsapp.templates`, media storage is `self.messenger.media`, and Instagram comments are `self.instagram.comments` (ADR-0025 rule 12). `wappa dev` continues importing `<module>:<app_var>.asgi`; the sibling `wappa_examples/simple_echo_example` uses that existing command with its Instagram host source. No new CLI command or hidden credential authority is introduced.

## Developer skills (`wappa/cli/skills/`)

The canonical source of Wappa's shipped Host skills: `wappa-apps` (the Platform-neutral core and router, with one reference per Platform and topic), `wappa-conversational-scores`, `wappa-state-and-storage`, `wappa-host-integration` and `wappa-scheduled-tasks`. Maintainer skills (`wappa-develop`, `bump-version`) live in `.agents/skills/` and never ship. Each has `SKILL.md`, directly linked `references/`, `agents/openai.yaml` and `evals/evals.json`. The repo root exposes them through relative symlinks in `.claude/skills/` and `.agents/skills/`. They are wheel package data, and `wappa init` copies them into the generated project's `.claude/skills/<name>` with an `.agents/skills/<name>` symlink, keeping any existing skill folder untouched (`_emit_skills`). `tests/test_shipped_skills.py` checks that every taught `from wappa… import …` and every `self.messenger` / `self.whatsapp` / `self.instagram` method exists, that no code block teaches `recipient=`, that frontmatter names match folders, that every reference is linked and every named sibling skill ships, that the isolation example runs, and that emission never overwrites. Lint with the `skills-engineering` linter (normal, `--professional` and `--lanes`) after each edit.
