"""ASGI server launch for ``wappa dev`` and ``wappa prod``."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

_SUPPORTED_SERVERS = frozenset({"uvicorn", "hypercorn"})


def _resolve_module_name(file_path: str) -> tuple[str, Path]:
    path = Path(file_path)
    if path.suffix == ".py":
        path = path.with_suffix("")
    module_name = str(path).replace(os.path.sep, ".")
    return module_name, Path(".")


def _build_uvicorn_cmd(
    import_string: str,
    host: str,
    port: int,
    workers: int,
    reload: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        import_string,
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")
    else:
        cmd.extend(["--workers", str(workers)])
    return cmd


def _build_hypercorn_cmd(
    import_string: str,
    host: str,
    port: int,
    workers: int,
    reload: bool,
) -> list[str]:
    bind = f"[::]:{port}" if host in ("0.0.0.0", "::") else f"{host}:{port}"
    cmd = [
        sys.executable,
        "-m",
        "hypercorn",
        import_string,
        "--bind",
        bind,
        "--workers",
        str(workers),
    ]
    if reload:
        cmd.append("--reload")
    return cmd


def _configured_log_dir() -> str:
    """``SYSTEM_LOG_DIR`` as the app will see it (process env, then ``.env``)."""
    from dotenv import dotenv_values

    return (
        os.getenv("SYSTEM_LOG_DIR")
        or dotenv_values(".env").get("SYSTEM_LOG_DIR")
        or "./logs"
    )


def _run_server(
    file_path: str,
    app_var: str,
    host: str,
    port: int,
    workers: int = 1,
    reload: bool = False,
    server: str = "uvicorn",
) -> None:
    if not Path(file_path).exists():
        typer.echo(f"❌ File not found: {file_path}", err=True)
        raise typer.Exit(1)

    server = server.lower()
    if server not in _SUPPORTED_SERVERS:
        typer.echo(
            f"❌ Unsupported server: {server}. Use 'uvicorn' or 'hypercorn'.",
            err=True,
        )
        raise typer.Exit(1)

    module_name, working_dir = _resolve_module_name(file_path)
    import_string = f"{module_name}:{app_var}.asgi"

    if server == "hypercorn":
        cmd = _build_hypercorn_cmd(import_string, host, port, workers, reload)
    else:
        cmd = _build_uvicorn_cmd(import_string, host, port, workers, reload)

    mode = "development" if reload else "production"

    typer.echo(f"🚀 Starting Wappa {mode} server ({server})...")
    typer.echo(f"📡 Import: {working_dir / module_name}:{app_var}.asgi")
    typer.echo(f"🌐 Server: http://{host}:{port}")

    if reload:
        typer.echo(f"📝 Docs: http://{host}:{port}/docs")
        log_dir = Path(working_dir, _configured_log_dir())
        typer.echo(
            f"📜 Live log: {log_dir / 'current.log'} · PIDs/port: {log_dir / 'dev.pid'}"
        )
    else:
        typer.echo(f"👥 Workers: {workers}")

    typer.echo("💡 Press CTRL+C to stop")
    typer.echo()

    try:
        subprocess.run(cmd, check=True, cwd=working_dir)
    except subprocess.CalledProcessError as e:
        typer.echo(
            f"❌ Server failed to start (exit code: {e.returncode})",
            err=True,
        )
        typer.echo("", err=True)
        typer.echo("Common issues:", err=True)
        typer.echo(f"• No module-level '{app_var}' variable in {file_path}", err=True)
        typer.echo(f"• Port {port} already in use", err=True)
        typer.echo(f"• Import errors in {file_path} or its dependencies", err=True)
        typer.echo("", err=True)
        typer.echo(
            f"Make sure your file has: {app_var} = Wappa(...) at module level", err=True
        )
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        typer.echo("👋 Server stopped")
