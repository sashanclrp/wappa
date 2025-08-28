"""
Wappa CLI main module.

Provides clean command-line interface for development and production workflows.
"""

import os
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(help="Wappa WhatsApp Business Framework CLI")


def _resolve_module_name(file_path: str) -> tuple[str, Path]:
    """
    Convert a file path to a Python module name and working directory.
    
    Handles both flat and nested project structures:
        main.py -> ("main", Path("."))
        app/main.py -> ("app.main", Path("."))  # Use dotted import from project root
        examples/redis_demo/main.py -> ("examples.redis_demo.main", Path("."))
    
    Returns:
        tuple[str, Path]: (module_name, working_directory)
    """
    # Convert to Path object for better handling
    path = Path(file_path)
    
    # Always use current directory as working dir and create dotted module name
    working_dir = Path(".")
    
    # Convert path to dotted module name (remove .py extension)
    if path.suffix == ".py":
        path = path.with_suffix("")
    
    # Convert path separators to dots for Python import
    module_name = str(path).replace(os.path.sep, ".")
    
    return module_name, working_dir


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
):
    """
    Run development server with auto-reload.

    Examples:
        wappa dev main.py
        wappa dev examples/redis_demo/main.py --port 8080
        wappa dev src/app.py --app my_wappa_app
    """
    # Validate file exists
    if not Path(file_path).exists():
        typer.echo(f"❌ File not found: {file_path}", err=True)
        raise typer.Exit(1)

    # Convert file path to module name and working directory
    module_name, working_dir = _resolve_module_name(file_path)
    import_string = f"{module_name}:{app_var}.asgi"

    # Build uvicorn command
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        import_string,
        "--reload",
        "--host",
        host,
        "--port",
        str(port),
    ]

    typer.echo(f"🚀 Starting Wappa development server...")
    typer.echo(f"📡 Import: {working_dir / module_name}:{app_var}.asgi")
    typer.echo(f"🌐 Server: http://{host}:{port}")
    typer.echo(f"📝 Docs: http://{host}:{port}/docs")
    typer.echo("💡 Press CTRL+C to stop")
    typer.echo()

    try:
        subprocess.run(cmd, check=True, cwd=working_dir)
    except subprocess.CalledProcessError as e:
        typer.echo(
            f"❌ Development server failed to start (exit code: {e.returncode})",
            err=True,
        )
        typer.echo("", err=True)
        typer.echo("Common issues:", err=True)
        typer.echo(f"• No module-level '{app_var}' variable in {file_path}", err=True)
        typer.echo(
            f"• Port {port} already in use (try --port with different number)", err=True
        )
        typer.echo(f"• Import errors in {file_path} or its dependencies", err=True)
        typer.echo("", err=True)
        typer.echo(
            f"Make sure your file has: {app_var} = Wappa(...) at module level", err=True
        )
        raise typer.Exit(1)
    except KeyboardInterrupt:
        typer.echo("👋 Development server stopped")


@app.command()
def run(
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
):
    """
    Run production server (no auto-reload).

    Examples:
        wappa run main.py
        wappa run main.py --workers 4 --port 8080
    """
    # Validate file exists
    if not Path(file_path).exists():
        typer.echo(f"❌ File not found: {file_path}", err=True)
        raise typer.Exit(1)

    # Convert file path to module name and working directory
    module_name, working_dir = _resolve_module_name(file_path)
    import_string = f"{module_name}:{app_var}.asgi"

    # Build uvicorn command (no reload for production)
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        import_string,
        "--host",
        host,
        "--port",
        str(port),
        "--workers",
        str(workers),
    ]

    typer.echo(f"🚀 Starting Wappa production server...")
    typer.echo(f"📡 Import: {working_dir / module_name}:{app_var}.asgi")
    typer.echo(f"🌐 Server: http://{host}:{port}")
    typer.echo(f"👥 Workers: {workers}")
    typer.echo("💡 Press CTRL+C to stop")
    typer.echo()

    try:
        subprocess.run(cmd, check=True, cwd=working_dir)
    except subprocess.CalledProcessError as e:
        typer.echo(
            f"❌ Production server failed to start (exit code: {e.returncode})",
            err=True,
        )
        typer.echo("", err=True)
        typer.echo("Common issues:", err=True)
        typer.echo(f"• No module-level '{app_var}' variable in {file_path}", err=True)
        typer.echo(f"• Port {port} already in use", err=True)
        typer.echo(f"• Import errors in {file_path} or its dependencies", err=True)
        raise typer.Exit(1)
    except KeyboardInterrupt:
        typer.echo("👋 Production server stopped")


@app.command()
def init(
    project_name: str = typer.Argument(..., help="Project name"),
    template: str = typer.Option(
        "basic", "--template", "-t", help="Project template (basic, redis)"
    ),
):
    """
    Initialize a new Wappa project (coming soon).

    Examples:
        wappa init my-whatsapp-bot
        wappa init my-bot --template redis
    """
    typer.echo("🚧 Project initialization coming soon!")
    typer.echo(f"Project: {project_name}")
    typer.echo(f"Template: {template}")
    typer.echo()
    typer.echo("For now, check out the examples directory for project templates.")


if __name__ == "__main__":
    app()
