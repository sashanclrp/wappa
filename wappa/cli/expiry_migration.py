"""CLI boundary for indexing live timers without re-arming them."""

import asyncio
import json

import typer

from wappa.persistence.redis.expiry_migration import migrate_expiry_index


def migrate_expiry_timers(
    redis_url: str = typer.Option(
        ...,
        "--redis-url",
        help="Explicit Redis URL; never inferred from the environment.",
    ),
    database: int = typer.Option(
        3,
        "--database",
        min=0,
        help="Expiry database (Wappa default: 3). Overrides the URL database.",
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Index live legacy timers (default: read-only dry run)."
    ),
    json_report: bool = typer.Option(
        False, "--json", help="Print counts as JSON; no key names or values."
    ),
) -> None:
    """Index existing qualified Expiry Keys, preserving values and remaining TTLs.

    Stop old timer writers first. Existing indexes are never overwritten;
    conflicts exit 1 and remain untouched. Expired legacy keys cannot be recovered.
    """
    try:
        report = asyncio.run(
            migrate_expiry_index(redis_url, apply=apply, database=database)
        )
    except Exception as exc:
        # Redis errors may contain connection details; do not echo them.
        typer.echo(
            f"Expiry migration failed ({type(exc).__name__}); no connection secrets were printed.",
            err=True,
        )
        raise typer.Exit(2) from None
    counts = report.to_dict()
    if json_report:
        typer.echo(json.dumps(counts))
    else:
        typer.echo("Applied expiry indexing" if apply else "Dry run: no keys changed")
        for name, count in counts.items():
            if name != "applied":
                typer.echo(f"{name}: {count}")
        if not apply:
            typer.echo("Re-run with --apply to index live timers.")
    if report.conflict:
        raise typer.Exit(1)
