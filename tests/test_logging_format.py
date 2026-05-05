"""
Tests for environment-aware logging (WappaJSONFormatter + setup_logging).

Verifies external observable behaviour only:
- JSON formatter emits valid single-line JSON per record
- exc_info is captured as an escaped string with no bare newlines
- Context prefixes [T:...][U:...] become structured fields
- setup_logging registers the right handler type per rich_format flag
- setup_app_logging respects SYSTEM_LOGS_RICH_FORMAT (via settings.logs_rich_format) and is_development fallback
"""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import patch

import pytest
from rich.logging import RichHandler

from wappa.core.logging.logger import WappaJSONFormatter, setup_app_logging, setup_logging


def _make_settings(*, is_development: bool, logs_rich_format: bool | None):
    return patch(
        "wappa.core.logging.logger.settings",
        log_level="INFO",
        log_dir="./logs",
        is_development=is_development,
        logs_rich_format=logs_rich_format,
    )


# ---------------------------------------------------------------------------
# WappaJSONFormatter unit tests
# ---------------------------------------------------------------------------


def _make_record(
    msg: str = "hello",
    level: int = logging.INFO,
    name: str = "test.logger",
    exc_info=None,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    return record


def test_json_formatter_produces_valid_json() -> None:
    fmt = WappaJSONFormatter()
    record = _make_record("simple message")
    line = fmt.format(record)
    obj = json.loads(line)
    assert obj["msg"] == "simple message"
    assert obj["level"] == "INFO"
    assert obj["logger"] == "test.logger"
    assert "ts" in obj


def test_json_formatter_single_line() -> None:
    fmt = WappaJSONFormatter()
    record = _make_record("no newlines please")
    line = fmt.format(record)
    assert "\n" not in line


def test_json_formatter_exc_info_single_line() -> None:
    fmt = WappaJSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = _make_record("error occurred", level=logging.ERROR, exc_info=sys.exc_info())

    line = fmt.format(record)
    assert "\n" not in line
    obj = json.loads(line)
    assert "exc" in obj
    assert "ValueError" in obj["exc"]
    assert "\\n" in obj["exc"]  # newlines are escaped, not bare


def test_json_formatter_no_exc_field_without_exception() -> None:
    fmt = WappaJSONFormatter()
    record = _make_record("clean record")
    obj = json.loads(fmt.format(record))
    assert "exc" not in obj


def test_json_formatter_parses_tenant_context_prefix() -> None:
    fmt = WappaJSONFormatter()
    record = _make_record("[T:15551234567] webhook failed")
    obj = json.loads(fmt.format(record))
    assert obj["tenant"] == "15551234567"
    assert obj["msg"] == "webhook failed"
    assert "user" not in obj


def test_json_formatter_parses_tenant_and_user_prefix() -> None:
    fmt = WappaJSONFormatter()
    record = _make_record("[T:111][U:999] done")
    obj = json.loads(fmt.format(record))
    assert obj["tenant"] == "111"
    assert obj["user"] == "999"
    assert obj["msg"] == "done"


def test_json_formatter_no_context_prefix() -> None:
    fmt = WappaJSONFormatter()
    record = _make_record("plain message without prefix")
    obj = json.loads(fmt.format(record))
    assert obj["msg"] == "plain message without prefix"
    assert "tenant" not in obj
    assert "user" not in obj


def test_json_formatter_ts_format() -> None:
    fmt = WappaJSONFormatter()
    record = _make_record("ts check")
    obj = json.loads(fmt.format(record))
    # Must be parseable as ISO-8601 (YYYY-MM-DDTHH:MM:SS)
    from datetime import datetime
    datetime.fromisoformat(obj["ts"])


# ---------------------------------------------------------------------------
# setup_logging handler-type tests
# ---------------------------------------------------------------------------


def _root_handler_types() -> list[type]:
    return [type(h) for h in logging.root.handlers]


def test_setup_logging_rich_format_attaches_rich_handler() -> None:
    setup_logging(level="INFO", rich_format=True)
    assert RichHandler in _root_handler_types()


def test_setup_logging_json_format_attaches_stream_handler() -> None:
    setup_logging(level="INFO", rich_format=False)
    types = _root_handler_types()
    assert RichHandler not in types
    assert logging.StreamHandler in types


def test_setup_logging_json_handler_uses_json_formatter() -> None:
    setup_logging(level="INFO", rich_format=False)
    stream_handlers = [h for h in logging.root.handlers if type(h) is logging.StreamHandler]
    assert stream_handlers, "no StreamHandler found"
    assert isinstance(stream_handlers[0].formatter, WappaJSONFormatter)


def test_setup_logging_json_output_is_valid_json() -> None:
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(WappaJSONFormatter())
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    old_level = root.level
    try:
        root.handlers = [handler]
        root.setLevel(logging.DEBUG)
        logging.getLogger("wappa.test").info("structured output")
        output = buf.getvalue().strip()
        json.loads(output)  # must not raise
    finally:
        root.handlers = old_handlers
        root.setLevel(old_level)


# ---------------------------------------------------------------------------
# setup_app_logging env-var precedence tests
# ---------------------------------------------------------------------------


def test_setup_app_logging_explicit_true_overrides_prod() -> None:
    with _make_settings(is_development=False, logs_rich_format=True):
        setup_app_logging()
    assert RichHandler in _root_handler_types()


def test_setup_app_logging_explicit_false_overrides_dev() -> None:
    with _make_settings(is_development=True, logs_rich_format=False):
        setup_app_logging()
    assert RichHandler not in _root_handler_types()


def test_setup_app_logging_no_override_development_uses_rich() -> None:
    with _make_settings(is_development=True, logs_rich_format=None):
        setup_app_logging()
    assert RichHandler in _root_handler_types()


def test_setup_app_logging_no_override_production_uses_json() -> None:
    with _make_settings(is_development=False, logs_rich_format=None):
        setup_app_logging()
    assert RichHandler not in _root_handler_types()
