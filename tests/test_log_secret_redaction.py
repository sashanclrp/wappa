"""OAuth secrets in third-party log lines (httpx URLs) never reach a handler."""

import logging

from wappa.core.logging.logger import SecretRedactingFilter, redact_secrets


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


def test_existing_partial_token_hints_stay_readable():
    assert redact_secrets("Bearer 12345678...wxyz") == "Bearer 12345678...wxyz"
