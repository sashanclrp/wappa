"""OAuth secrets in third-party log lines (httpx URLs) never reach a handler."""

import io
import logging

import httpx
import pytest

from wappa.core.logging.logger import (
    SecretRedactingFilter,
    _console,
    redact_secrets,
    setup_logging,
)


def test_query_secrets_and_bearer_tokens_are_masked():
    line = (
        "HTTP Request: GET https://graph.facebook.com/v26.0/debug_token"
        "?input_token=EAAsecret&access_token=app|sec&code=AQ123&client_secret=abc"
        '&fields=id "HTTP/1.1 200 OK" Authorization: Bearer EAAxyz1234567890abcdefgh'
    )
    out = redact_secrets(line)
    for secret in ("EAAsecret", "app|sec", "AQ123", "abc&", "EAAxyz1234567890abcdefgh"):
        assert secret not in out
    assert "fields=id" in out and "HTTP/1.1 200 OK" in out


def test_filter_rewrites_formatted_records():
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        "HTTP Request: %s %s",
        ("GET", "https://x/?access_token=EAAz"),
        None,
    )
    assert SecretRedactingFilter().filter(record)
    assert record.getMessage() == "HTTP Request: GET https://x/?access_token=[REDACTED]"


def test_ordinary_code_fields_are_kept():
    assert (
        redact_secrets("error_code=100 status_code=200")
        == "error_code=100 status_code=200"
    )
    line = "FORMAT_SEND outcome=rejected code=131053 message_ids=-"
    assert redact_secrets(line) == line


def test_oauth_code_is_masked_as_the_first_query_parameter():
    out = redact_secrets("GET https://x/connect/instagram/callback?code=AQ123&state=s")
    assert "AQ123" not in out and "state=s" in out


def test_existing_partial_token_hints_stay_readable():
    assert redact_secrets("Bearer 12345678...wxyz") == "Bearer 12345678...wxyz"


# ---------------------------------------------------------------------------
# End-to-end: a real httpx request through Wappa's configured handlers
# ---------------------------------------------------------------------------

_ACCESS_TOKEN = "EAAGaccessTokenValue1234567890"
_CLIENT_SECRET = "clientSecretValue0987654321"
_OAUTH_CODE = "AQDoauthCodeValue1122334455"
_BEARER = "EAAB" + "x7" * 18  # 40 characters
_SECRETS = (_ACCESS_TOKEN, _CLIENT_SECRET, _OAUTH_CODE, _BEARER)
_SECRET_URL = (
    "https://graph.facebook.com/v26.0/oauth/access_token"
    f"?client_id=123&client_secret={_CLIENT_SECRET}"
    f"&code={_OAUTH_CODE}&access_token={_ACCESS_TOKEN}"
)


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield root
    for handler in root.handlers:
        handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def _emit_secret_traffic() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    with httpx.Client(transport=transport) as client:
        response = client.get(_SECRET_URL)
    assert response.status_code == 200
    logging.getLogger("httpx").debug(
        "Request headers: Authorization: Bearer %s", _BEARER
    )


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_json_handler_never_writes_secrets_from_httpx(level, restore_root_logging):
    setup_logging(level=level, mode="PROD", rich_format=False)
    stream = io.StringIO()
    stream_handlers = [
        h for h in restore_root_logging.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert stream_handlers
    for handler in stream_handlers:
        handler.setStream(stream)

    _emit_secret_traffic()

    captured = stream.getvalue()
    assert "HTTP Request: GET" in captured, "httpx request line was not captured"
    if level == "DEBUG":
        assert "Authorization: Bearer [REDACTED]" in captured
    for secret in _SECRETS:
        assert secret not in captured


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_rich_console_and_dev_file_never_write_secrets_from_httpx(
    level, restore_root_logging, tmp_path
):
    with _console.capture() as console_capture:
        setup_logging(level=level, mode="DEV", log_dir=str(tmp_path), rich_format=True)
        _emit_secret_traffic()
    for handler in restore_root_logging.handlers:
        handler.flush()

    file_text = "".join(p.read_text() for p in tmp_path.glob("*.log"))
    for captured in (console_capture.get(), file_text):
        # Rich wraps long lines; compare without whitespace so a wrapped
        # secret is still found.
        compact = "".join(captured.split())
        assert "HTTPRequest:GET" in compact, "httpx request line was not captured"
        if level == "DEBUG":
            assert "Authorization:Bearer[REDACTED]" in compact
        for secret in _SECRETS:
            assert secret not in compact
