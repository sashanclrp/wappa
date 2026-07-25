"""Generic HMAC signature verification for External Webhook Sources.

Most signed webhook providers (Stripe, Wompi, GitHub, Shopify, MercadoPago's
signed variants) reduce to the same shape: an HMAC of the raw request body
under a shared secret, carried in a header, optionally prefixed with the
algorithm name and encoded as hex or base64.

``HMACSignatureVerifier`` covers that shape so an ``IWebhookProcessor`` does
not have to re-implement constant-time comparison and encoding handling.
Providers that sign something other than the raw body (a timestamped payload,
a canonical string) can build that string themselves and pass it as ``payload``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from collections.abc import Mapping
from typing import Literal

SignatureEncoding = Literal["hex", "base64"]

_SUPPORTED_ALGORITHMS = frozenset(hashlib.algorithms_guaranteed)


class HMACSignatureVerifier:
    """Verify an HMAC signature carried in a request header.

    Args:
        secret: Shared signing secret. Empty secrets are rejected — a webhook
            "verified" against an empty secret is worse than no verification.
        header: Header carrying the signature, e.g. ``X-Signature``.
        algorithm: Any ``hashlib`` algorithm name. Defaults to ``sha256``.
        prefix: Optional prefix stripped from the header value before
            comparison, e.g. ``sha256=`` for GitHub-style signatures.
        encoding: ``hex`` (default) or ``base64`` digest encoding.

    Example:
        verifier = HMACSignatureVerifier(
            secret=settings.stripe_webhook_secret,
            header="Stripe-Signature",
        )

        class StripeProcessor:
            async def parse_event(self, request, inbox_id):
                body = await request.body()
                if not verifier.verify(body, request.headers):
                    raise ValueError("invalid Stripe webhook signature")
                ...
    """

    def __init__(
        self,
        secret: str | bytes,
        *,
        header: str,
        algorithm: str = "sha256",
        prefix: str = "",
        encoding: SignatureEncoding = "hex",
    ) -> None:
        secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not secret_bytes:
            raise ValueError("secret must be a non-empty string or bytes")
        if not header or not header.strip():
            raise ValueError("header must be a non-empty string")
        if algorithm not in _SUPPORTED_ALGORITHMS:
            raise ValueError(f"unsupported hash algorithm: {algorithm!r}")
        if encoding not in ("hex", "base64"):
            raise ValueError(f"unsupported signature encoding: {encoding!r}")

        self._secret = secret_bytes
        self.header = header.strip()
        self.algorithm = algorithm
        self.prefix = prefix
        self.encoding: SignatureEncoding = encoding

    def sign(self, payload: bytes) -> str:
        """Return the expected signature for ``payload``, without the prefix."""
        return self._encode(self._digest(payload))

    def verify(self, payload: bytes, headers: Mapping[str, str]) -> bool:
        """Return True when ``headers`` carry a valid signature for ``payload``.

        Returns False for a missing header, a wrong prefix, an undecodable
        signature, and a mismatching digest. It never raises on bad input:
        callers should translate a False result into their own rejection.
        """
        provided = headers.get(self.header)
        if provided is None:
            # Starlette headers are case-insensitive, but plain dicts are not.
            provided = _case_insensitive_get(headers, self.header)
        if not provided:
            return False
        return self.verify_signature(payload, provided)

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Return True when ``signature`` is valid for ``payload``."""
        candidate = signature.strip()
        if self.prefix:
            if not candidate.startswith(self.prefix):
                return False
            candidate = candidate.removeprefix(self.prefix)
        if not candidate:
            return False

        # Compare raw digest bytes so hex casing and base64 padding variants
        # do not cause false rejections, and so the expected digest never has
        # to be encoded to a string and decoded straight back.
        provided_digest = _decode(candidate, self.encoding)
        if provided_digest is None:
            return False
        expected_digest = self._digest(payload)
        return hmac.compare_digest(expected_digest, provided_digest)

    def _digest(self, payload: bytes) -> bytes:
        return hmac.new(self._secret, payload, self.algorithm).digest()

    def _encode(self, digest: bytes) -> str:
        if self.encoding == "base64":
            return base64.b64encode(digest).decode("ascii")
        return digest.hex()


def _decode(value: str, encoding: SignatureEncoding) -> bytes | None:
    try:
        if encoding == "base64":
            return base64.b64decode(value, validate=True)
        return bytes.fromhex(value)
    except (ValueError, binascii.Error):
        return None


def _case_insensitive_get(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None
