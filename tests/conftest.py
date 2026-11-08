"""Shared test configuration.

The suite is hermetic: it never reads a developer's ``.env``. Everything here
runs before any test module imports Wappa, so ``wappa.core.config.settings``
sees only the process environment plus the dummy defaults below.
"""

import os

import dotenv
import pytest

# ``wappa.core.config.settings`` calls ``load_dotenv(".env")`` at import time.
# Disable it so a real ``.env`` (with an explicit routing mode, a Redis URL,
# a different log level, real tokens...) cannot change test results.
dotenv.load_dotenv = lambda *args, **kwargs: False

# Dummy, non-secret legacy single-Inbox bundle. Tests that build a Wappa app
# in legacy mode need it; real values never belong in the test run.
_TEST_ENV_DEFAULTS = {
    "META_WHATSAPP_ACCESS_TOKEN": "test-access-token",
    "META_WHATSAPP_PHONE_NUMBER_ID": "100000000000001",
    "META_WHATSAPP_BUSINESS_ACCOUNT_ID": "200000000000002",
    "META_WEBHOOK_VERIFY_TOKEN": "test-verify-token",
    "META_APP_SECRET": "test-app-secret",
    # Meta payload drift fails tests instead of being logged (ADR-0023):
    # fixtures must model every field Meta sends.
    "SYSTEM_STRICT_META_SCHEMA": "1",
}

for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True)
def _fresh_rate_governor():
    """Rate-limit state is process-wide: give every test its own, unpaced."""
    from wappa.resilience.rate_limits import (
        RateLimitGovernor,
        RateLimitPolicy,
        rate_governor,
        use_rate_governor,
    )

    previous = rate_governor()
    use_rate_governor(RateLimitGovernor(RateLimitPolicy(send_rates=None)))
    yield
    use_rate_governor(previous)
