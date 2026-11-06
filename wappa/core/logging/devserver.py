"""Dev-server handles: the ``current.log`` symlink and the ``dev.pid`` record."""

from __future__ import annotations

import atexit
import os
import sys
from datetime import datetime
from pathlib import Path

from wappa.core.config.settings import settings

CURRENT_LOG_NAME = "current.log"
DEV_PID_NAME = "dev.pid"
_dev_pidfile: tuple[Path, int] | None = None


def point_current_log(log_dir: str | os.PathLike[str], logfile: str) -> Path | None:
    """Atomically repoint ``<log_dir>/current.log`` at ``logfile``.

    The link is relative, so the folder can be moved. A Platform without
    symlinks (or a read-only folder) keeps logging; readers then fall back to
    the newest ``wappa_*.log``.
    """
    link = Path(log_dir) / CURRENT_LOG_NAME
    tmp = link.with_name(f".{CURRENT_LOG_NAME}.{os.getpid()}.tmp")
    try:
        tmp.unlink(missing_ok=True)
        os.symlink(Path(logfile).name, tmp)
        os.replace(tmp, link)
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    return link


def _detect_server_port(argv: list[str]) -> tuple[int, str]:
    """Port from the ASGI server's command line, else ``PORT``/settings.

    uvicorn's reload worker is spawned with the parent's ``sys.argv``, so
    ``--port``/``--bind`` are visible in the serving process too.
    """
    for index, arg in enumerate(argv):
        value: str | None = None
        if arg in {"--port", "--bind", "-b"} and index + 1 < len(argv):
            value = argv[index + 1]
        elif arg.startswith(("--port=", "--bind=")):
            value = arg.split("=", 1)[1]
        if value:
            candidate = value.rsplit(":", 1)[-1]
            if candidate.isdigit():
                return int(candidate), "argv"
    return settings.port, "PORT"


def _parent_role(argv: list[str], parent_pid: int) -> str:
    if "--reload" in argv:
        return "reloader"
    try:
        cmdline = Path(f"/proc/{parent_pid}/cmdline").read_bytes()
    except OSError:
        return "launcher"
    return "reloader" if b"--reload" in cmdline else "launcher"


def write_dev_pidfile(
    log_dir: str | os.PathLike[str], *, log_file: str | None = None
) -> Path:
    """Record who serves this dev app: ``<log_dir>/dev.pid`` (key=value lines).

    ``serving_pid`` runs the app. ``parent_pid`` is the uvicorn reloader under
    ``--reload`` (it respawns the worker) or whatever launched the server.
    ``stop_pid`` is the one to signal to stop the whole dev server. The file
    is removed on clean shutdown (``release_dev_pidfile``).
    """
    argv = list(sys.argv)
    serving_pid, parent_pid = os.getpid(), os.getppid()
    role = _parent_role(argv, parent_pid)
    port, port_source = _detect_server_port(argv)
    lines = {
        "serving_pid": serving_pid,
        "parent_pid": parent_pid,
        "parent_role": role,
        "stop_pid": parent_pid if role == "reloader" else serving_pid,
        "port": port,
        "port_source": port_source,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "log_file": log_file or "",
    }
    path = Path(log_dir) / DEV_PID_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{DEV_PID_NAME}.{serving_pid}.tmp")
    tmp.write_text("".join(f"{k}={v}\n" for k, v in lines.items()), encoding="utf-8")
    os.replace(tmp, path)
    global _dev_pidfile
    _dev_pidfile = (path, serving_pid)
    # Backup only: uvicorn re-raises SIGTERM/SIGINT after a graceful shutdown,
    # which skips atexit, so the core shutdown hook calls release_dev_pidfile.
    atexit.register(remove_dev_pidfile, path, serving_pid)
    return path


def release_dev_pidfile() -> bool:
    """Remove the ``dev.pid`` this process wrote, if any (clean shutdown)."""
    global _dev_pidfile
    if _dev_pidfile is None:
        return False
    path, serving_pid = _dev_pidfile
    _dev_pidfile = None
    return remove_dev_pidfile(path, serving_pid)


def remove_dev_pidfile(path: str | os.PathLike[str], serving_pid: int) -> bool:
    """Delete ``dev.pid`` only while it still names ``serving_pid``.

    A reload starts the next worker after the old one exits, but a crashed
    worker's late cleanup must never delete its successor's record.
    """
    pid_path = Path(path)
    try:
        content = pid_path.read_text(encoding="utf-8")
    except OSError:
        return False
    if f"serving_pid={serving_pid}\n" not in content:
        return False
    try:
        pid_path.unlink(missing_ok=True)
    except OSError:
        return False
    return True
