"""Shared test configuration.

The suite is hermetic: it never reads a developer's ``.env``. Everything here
runs before any test module imports Wappa, so ``wappa.core.config.settings``
sees only the process environment plus the dummy defaults below.
"""

import os

import dotenv

# ``wappa.core.config.settings`` calls ``load_dotenv(".env")`` at import time.
# Disable it so a real ``.env`` (with an explicit routing mode, a Redis URL,
# a different log level, real tokens...) cannot change test results.
dotenv.load_dotenv = lambda *args, **kwargs: False

# Dummy, non-secret legacy single-Inbox bundle. Tests that build a Wappa app
# in legacy mode need it; real values never belong in the test run.
_TEST_ENV_DEFAULTS = {
    "WP_ACCESS_TOKEN": "test-access-token",
    "WP_PHONE_ID": "100000000000001",
    "WP_BID": "200000000000002",
    "WP_WEBHOOK_VERIFY_TOKEN": "test-verify-token",
    "META_APP_SECRET": "test-app-secret",
    # Meta payload drift fails tests instead of being logged (ADR-0023):
    # fixtures must model every field Meta sends.
    "WAPPA_STRICT_META_SCHEMA": "1",
}

for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
