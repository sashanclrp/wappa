"""Wappa CLI: the Typer ``app`` and its thin command definitions."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from .examples_catalog import _show_examples_menu
from .scaffold import _initialize_project
from .serve import _run_server

app = typer.Typer(help="Wappa WhatsApp Business Framework CLI")
console = Console()


@app.command()
def dev(
    file_path: str = typer.Argument(
        ..., help="Path to your Python file (e.g., main.py)"
    ),
    app_var: str = typer.Option(
        "app", "--app", "-a", help="Wappa instance variable name"
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    server: str = typer.Option(
        "uvicorn",
        "--server",
        "-s",
        help="ASGI server backend (uvicorn or hypercorn)",
        envvar="WAPPA_SERVER",
    ),
) -> None:
    _run_server(file_path, app_var, host, port, reload=True, server=server)


@app.command()
def prod(
    file_path: str = typer.Argument(
        ..., help="Path to your Python file (e.g., main.py)"
    ),
    app_var: str = typer.Option(
        "app", "--app", "-a", help="Wappa instance variable name"
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of worker processes"
    ),
    server: str = typer.Option(
        "uvicorn",
        "--server",
        "-s",
        help="ASGI server backend (uvicorn or hypercorn)",
        envvar="WAPPA_SERVER",
    ),
) -> None:
    _run_server(
        file_path, app_var, host, port, workers=workers, reload=False, server=server
    )


@app.command()
def init(
    directory: str = typer.Argument(
        ".", help="Directory to initialize (default: current directory)"
    ),
    inbox_routing: str = typer.Option(
        "legacy",
        "--inbox-routing",
        help="Credential authority for the generated project: legacy or explicit.",
    ),
) -> None:
    if inbox_routing not in {"legacy", "explicit"}:
        raise typer.BadParameter("must be 'legacy' or 'explicit'")
    _initialize_project(directory, inbox_routing=inbox_routing)


@app.command()
def examples(
    directory: str = typer.Argument(
        ".", help="Directory to copy example to (default: current directory)"
    ),
) -> None:
    _show_examples_menu(directory)


migrate_app = typer.Typer(help="One-off data migrations between Wappa releases")
app.add_typer(migrate_app, name="migrate")


@migrate_app.command("cache-namespaces")
def migrate_cache_namespaces(
    whatsapp_inbox: list[str] = typer.Option(
        ...,
        "--whatsapp-inbox",
        "-i",
        help="WhatsApp phone_number_id whose pre-0.34 keys to rename (repeatable)",
    ),
    redis_url: str | None = typer.Option(
        None,
        "--redis-url",
        envvar="REDIS_URL",
        help="Redis base URL without a database number (default: REDIS_URL)",
    ),
    json_root: Path | None = typer.Option(
        None, "--json-root", help="JSON cache root folder (the JSON backend's cache/)"
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Rename for real (default: dry run, change nothing)"
    ),
    json_report: bool = typer.Option(
        False, "--json", help="Print the complete report as JSON on stdout"
    ),
) -> None:
    """Rename WhatsApp cache keys from <pnid> to whatsapp__<pnid> (0.33 -> 0.34).

    Stop every 0.33 worker first. Keys keep their TTL; existing qualified
    keys are never overwritten (reported as conflicts). Exits with status 1
    when any conflict remains, on a dry run too; resolve them before cutover.
    """
    import asyncio
    import json

    from wappa.persistence.namespace_migration import (
        migrate_json_namespaces,
        migrate_redis_namespaces,
    )

    if not redis_url and json_root is None:
        console.print("❌ Give --redis-url (or REDIS_URL) and/or --json-root")
        raise typer.Exit(2)
    reports = []
    if redis_url:
        reports.append(
            (
                "Redis",
                asyncio.run(
                    migrate_redis_namespaces(redis_url, whatsapp_inbox, apply=apply)
                ),
            )
        )
    if json_root is not None:
        reports.append(
            ("JSON", migrate_json_namespaces(json_root, whatsapp_inbox, apply=apply))
        )
    has_conflicts = any(report.conflicts for _, report in reports)
    if json_report:
        typer.echo(
            json.dumps(
                {
                    "applied": apply,
                    "has_conflicts": has_conflicts,
                    "backends": {
                        backend: {
                            "renamed": [list(pair) for pair in report.renamed],
                            "conflicts": report.conflicts,
                        }
                        for backend, report in reports
                    },
                }
            )
        )
        if has_conflicts:
            raise typer.Exit(1)
        return
    verb = "Renamed" if apply else "Would rename"
    for backend, report in reports:
        console.print(f"[bold]{backend}[/bold]: {verb} {len(report.renamed)} keys")
        for old, new in report.renamed[:20]:
            console.print(f"  {old} -> {new}")
        if len(report.renamed) > 20:
            console.print(f"  ... and {len(report.renamed) - 20} more")
        if report.conflicts:
            console.print(
                f"[yellow]{len(report.conflicts)} target keys already exist "
                "(left untouched):[/yellow]"
            )
            for key in report.conflicts[:20]:
                console.print(f"  {key}")
            if len(report.conflicts) > 20:
                console.print(
                    f"  ... and {len(report.conflicts) - 20} more (--json lists all)"
                )
    if not apply:
        console.print("Dry run only. Re-run with --apply to rename.")
    if has_conflicts:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
