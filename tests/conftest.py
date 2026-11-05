"""Shared test configuration."""

import os

# Meta payload drift fails tests instead of being logged (ADR-0010): fixtures
# must model every field Meta sends.
os.environ.setdefault("WAPPA_STRICT_META_SCHEMA", "1")
