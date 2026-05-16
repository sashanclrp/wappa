# CLI Context — Glossary

Terms specific to the `wappa/cli` context. For root-level canonical terms (`inbox_id`, **Host Application**, **WappaEventHandler**, etc.) see the root `CONTEXT.md`.

| Term | Definition |
|---|---|
| **CLI** | The `wappa` command-line tool exposed as a console script entry point. |
| **Command** | A top-level CLI sub-command: `init`, `examples`, `dev`, `prod`. |
| **Scaffolded Project** | The minimal Host Application directory structure created by `wappa init`. |
| **Template** | A static file under `cli/templates/` rendered verbatim into a scaffolded project. |
| **Example** | A complete, runnable Host Application under `cli/examples/` that demonstrates a specific Wappa feature set. It is copied to the target directory by `wappa examples`. |
| **Example Key** | The directory name of an example (e.g. `simple_echo_example`). Used internally to locate the source directory. |
| **Import String** | The Python module path and ASGI attribute passed to the ASGI server (e.g. `app.main:app.asgi`). Derived from the file path argument at server startup. |
| **ASGI Server** | The HTTP server process spawned by `dev` or `prod`. Supported values: `uvicorn`, `hypercorn`. Selectable via `--server` or `WAPPA_SERVER` env var. |
| **Dev Mode** | Server started with `--reload` enabled and a single worker. Used for local development. |
| **Prod Mode** | Server started without `--reload`, with configurable worker count. Used for deployment. |
| **Safe Existing Files** | Files ignored during non-empty directory checks: `pyproject.toml`, `uv.lock`, `README.md`. |
| **Scores Directory** | `app/scores/` — placeholder directory created inside a scaffolded project for Host Application business logic. Wappa does not read or own this directory. |
