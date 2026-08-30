"""Raw-body authentication for Meta POST callbacks.

Meta signs the exact request bytes with the App Secret:
``X-Hub-Signature-256: sha256=<hex HMAC-SHA256>``. Wappa verifies those bytes
before JSON parsing, directory reads, logging of payload content, or any work
scheduling. Missing, malformed, and mismatched signatures are indistinguishable
to the caller.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Final

from pydantic import SecretStr

SIGNATURE_HEADER: Final[str] = "X-Hub-Signature-256"
SIGNATURE_SCHEME: Final[str] = "sha256="
_HEX_DIGEST_LENGTH: Final[int] = 64


class MetaCallbackAuthenticator:
    """Constant-time HMAC-SHA256 verification of Meta callback bodies."""

    def __init__(self, app_secret: SecretStr) -> None:
        secret = app_secret.get_secret_value()
        if not secret:
            raise ValueError("app_secret must not be empty")
        self._secret = secret.encode("utf-8")

    def sign(self, body: bytes) -> str:
        """Return the header value Meta would send for ``body``."""
        digest = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return f"{SIGNATURE_SCHEME}{digest}"

    def verify(self, body: bytes, signature_header: str | None) -> bool:
        """Whether ``signature_header`` proves ``body`` came from the Meta App."""
        if not signature_header or not signature_header.startswith(SIGNATURE_SCHEME):
            return False
        provided = signature_header[len(SIGNATURE_SCHEME) :].strip().lower()
        if len(provided) != _HEX_DIGEST_LENGTH:
            return False
        try:
            provided_digest = bytes.fromhex(provided)
        except ValueError:
            return False
        expected = hmac.new(self._secret, body, hashlib.sha256).digest()
        return hmac.compare_digest(expected, provided_digest)


__all__ = ["SIGNATURE_HEADER", "SIGNATURE_SCHEME", "MetaCallbackAuthenticator"]
