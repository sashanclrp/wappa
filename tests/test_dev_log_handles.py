"""Stable dev log handles: ``logs/current.log`` and ``logs/dev.pid``."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from wappa.core.logging import devserver
from wappa.core.logging.devserver import (
    CURRENT_LOG_NAME,
    DEV_PID_NAME,
    point_current_log,
    release_dev_pidfile,
    remove_dev_pidfile,
    write_dev_pidfile,
)
from wappa.core.logging.file_handlers import DailyFileHandler
from wappa.core.logging.logger import setup_app_logging


def _record(created: float, msg: str = "line") -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, "", 0, msg, (), None)
    record.created = created
    return record


def _pidfile(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
    )


def test_handler_points_current_log_at_todays_file(tmp_path: Path) -> None:
    handler = DailyFileHandler(tmp_path)
    try:
        handler.emit(_record(time.time(), "hello"))
    finally:
        handler.close()

    link = tmp_path / CURRENT_LOG_NAME
    assert link.is_symlink()
    assert os.readlink(link) == f"wappa_{datetime.now():%Y%m%d}.log"
    assert "hello" in link.read_text(encoding="utf-8")


def test_rollover_moves_current_log_and_leaves_the_old_file(tmp_path: Path) -> None:
    handler = DailyFileHandler(tmp_path)
    tomorrow = datetime.now() + timedelta(days=1)
    try:
        handler.emit(_record(time.time(), "today"))
        old = Path(handler.baseFilename)
        old_inode = old.stat().st_ino
        handler.emit(_record(tomorrow.timestamp(), "tomorrow"))
    finally:
        handler.close()

    assert os.readlink(tmp_path / CURRENT_LOG_NAME) == f"wappa_{tomorrow:%Y%m%d}.log"
    assert old.stat().st_ino == old_inode
    assert "tomorrow" not in old.read_text(encoding="utf-8")
    assert "tomorrow" in (tmp_path / CURRENT_LOG_NAME).read_text(encoding="utf-8")


def test_repointing_replaces_the_link_atomically(tmp_path: Path) -> None:
    (tmp_path / "wappa_20260101.log").write_text("a")
    (tmp_path / "wappa_20260102.log").write_text("b")

    point_current_log(tmp_path, str(tmp_path / "wappa_20260101.log"))
    point_current_log(tmp_path, str(tmp_path / "wappa_20260102.log"))

    assert (tmp_path / CURRENT_LOG_NAME).read_text() == "b"
    assert not list(tmp_path.glob(".current.log.*"))


def test_pidfile_labels_reloader_parent_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["uvicorn", "app.main:app.asgi", "--port", "8123", "--reload"]
    )
    registered: list[tuple] = []
    monkeypatch.setattr(devserver.atexit, "register", lambda *a: registered.append(a))

    path = write_dev_pidfile(tmp_path, log_file="/x/wappa_1.log")

    data = _pidfile(path)
    assert path == tmp_path / DEV_PID_NAME
    assert data["serving_pid"] == str(os.getpid())
    assert data["parent_pid"] == str(os.getppid())
    assert data["parent_role"] == "reloader"
    assert data["stop_pid"] == data["parent_pid"]
    assert (data["port"], data["port_source"]) == ("8123", "argv")
    assert registered == [(remove_dev_pidfile, path, os.getpid())]


def test_hypercorn_bind_port_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["hypercorn", "m:app", "--bind", "[::]:8443"])
    monkeypatch.setattr(devserver.atexit, "register", lambda *a: None)

    data = _pidfile(write_dev_pidfile(tmp_path))

    assert data["port"] == "8443"


def test_pidfile_removed_only_by_its_own_server(tmp_path: Path) -> None:
    path = tmp_path / DEV_PID_NAME
    path.write_text("serving_pid=111\nport=8000\n")

    assert remove_dev_pidfile(path, 222) is False
    assert path.exists()
    assert remove_dev_pidfile(path, 111) is True
    assert not path.exists()


def test_release_removes_the_file_this_process_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clean shutdown path: uvicorn re-raises SIGTERM, so atexit is not enough."""
    monkeypatch.setattr(devserver.atexit, "register", lambda *a: None)
    path = write_dev_pidfile(tmp_path)

    assert release_dev_pidfile() is True
    assert not path.exists()
    assert release_dev_pidfile() is False


def test_setup_app_logging_in_dev_writes_both_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["python", "-m", "app.main"])
    monkeypatch.setattr(devserver.atexit, "register", lambda *a: None)
    root = logging.getLogger()
    saved = root.handlers[:]
    try:
        with (
            patch(
                "wappa.core.logging.logger.settings",
                log_level="INFO",
                log_dir=str(tmp_path),
                is_development=True,
                logs_rich_format=None,
                port=8765,
            ),
            patch("wappa.core.logging.devserver.settings", port=8765),
        ):
            setup_app_logging()
        logging.getLogger("wappa.test").info("after setup")
        for handler in root.handlers:
            handler.flush()
        current = tmp_path / CURRENT_LOG_NAME
        assert "after setup" in current.read_text(encoding="utf-8")
        data = _pidfile(tmp_path / DEV_PID_NAME)
        assert (data["port"], data["port_source"]) == ("8765", "PORT")
        assert data["log_file"] == os.path.realpath(current)
    finally:
        for handler in root.handlers:
            if handler not in saved:
                handler.close()
        root.handlers = saved
