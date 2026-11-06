"""Server launch for ``Wappa.run``: production uvicorn and the dev reload subprocess."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Any

import uvicorn

from .config.settings import settings
from .logging.logger import get_app_logger

if TYPE_CHECKING:
    from .wappa_app import Wappa

# Frames in these modules belong to Wappa; the first frame outside them is the
# Host script that dev mode re-imports.
_SKIPPED_MODULES = frozenset({__name__, "wappa.core.wappa_app"})


def run_production(app: Wappa, host: str, port: int, **kwargs: Any) -> None:
    """Run in production mode without auto-reload."""
    logger = get_app_logger()

    uvicorn_config = {
        "host": host,
        "port": port,
        "reload": False,
        "log_level": settings.log_level.lower(),
        **kwargs,
    }

    logger.info("Starting production server with .asgi property...")
    # Use the .asgi property which handles sync build + lifespan initialization
    uvicorn.run(app.asgi, **uvicorn_config)


def run_dev_mode(app: Wappa, host: str, port: int, **kwargs: Any) -> None:
    """
    Run in development mode with uvicorn auto-reload.

    Uses uvicorn with import string for proper reload functionality.
    Requires module-level 'app' variable containing Wappa instance.
    """
    import inspect

    logger = get_app_logger()

    # Get the calling module to build import string
    frame = inspect.currentframe()
    while frame and frame.f_globals.get("__name__") in _SKIPPED_MODULES:
        frame = frame.f_back

    if not frame:
        logger.error("❌ Cannot detect calling script for dev mode")
        raise RuntimeError(
            "Cannot locate calling script for dev mode.\n"
            "Make sure you're running from a Python file, not a REPL."
        )

    module_name = frame.f_globals.get("__name__")
    if module_name in (None, "__main__"):
        # Try to guess from file path
        file_path = frame.f_globals.get("__file__")
        if not file_path:
            raise RuntimeError("Dev mode requires running from a file, not a REPL.")

        # Convert file path to module name (e.g., examples/main.py -> examples.main)
        import os.path

        module_name = (
            os.path.splitext(os.path.relpath(file_path))[0]
            .replace(os.sep, ".")
            .lstrip(".")
        )

    # Build uvicorn command with import string
    import_string = f"{module_name}:app.asgi"
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
        "--log-level",
        settings.log_level.lower(),
    ]

    # Add additional kwargs
    for key, value in kwargs.items():
        if key != "reload":  # Skip reload, we're handling it
            cmd.extend([f"--{key.replace('_', '-')}", str(value)])

    logger.info(f"🚀 Starting dev server: {' '.join(cmd)}")
    logger.info(f"📡 Import string: {import_string}")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Uvicorn failed to start (exit code: {e.returncode})")
        raise RuntimeError(
            f"Development server failed to start.\n\n"
            f"Common causes:\n"
            f"• No module-level 'app' variable found in {module_name}\n"
            f"• Port {port} already in use\n"
            f"• Import errors in your script\n\n"
            f"Make sure you have: app = Wappa(...) at module level."
        ) from e
    except KeyboardInterrupt:
        logger.info("👋 Development server stopped by user")
