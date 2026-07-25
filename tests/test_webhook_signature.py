"""Tests for the generic HMAC verifier used by External Webhook Sources."""

from __future__ import annotations

import base64
import hashlib
import hmac

import pytest
from starlette.datastructures import Headers

from wappa import HMACSignatureVerifier

SECRET = "top-secret"
BODY = b'{"event":"payment.approved","id":"42"}'


def _hex_signature(secret: str = SECRET, body: bytes = BODY) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_is_accepted() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature")
    assert verifier.verify(BODY, {"X-Signature": _hex_signature()}) is True


def test_header_lookup_is_case_insensitive_for_plain_dicts() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature")
    assert verifier.verify(BODY, {"x-signature": _hex_signature()}) is True


def test_starlette_headers_are_supported() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature")
    headers = Headers({"x-signature": _hex_signature()})
    assert verifier.verify(BODY, headers) is True


def test_tampered_body_is_rejected() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature")
    assert (
        verifier.verify(b'{"amount":999}', {"X-Signature": _hex_signature()}) is False
    )


def test_wrong_secret_is_rejected() -> None:
    verifier = HMACSignatureVerifier("other-secret", header="X-Signature")
    assert verifier.verify(BODY, {"X-Signature": _hex_signature()}) is False


def test_missing_header_is_rejected() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature")
    assert verifier.verify(BODY, {}) is False
    assert verifier.verify(BODY, {"X-Signature": ""}) is False


def test_malformed_signature_is_rejected_without_raising() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature")
    assert verifier.verify(BODY, {"X-Signature": "not-hex-at-all"}) is False


def test_hex_casing_does_not_change_the_verdict() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature")
    assert verifier.verify(BODY, {"X-Signature": _hex_signature().upper()}) is True


def test_prefixed_signature_requires_the_prefix() -> None:
    verifier = HMACSignatureVerifier(
        SECRET, header="X-Hub-Signature-256", prefix="sha256="
    )
    signature = _hex_signature()

    assert verifier.verify(BODY, {"X-Hub-Signature-256": f"sha256={signature}"}) is True
    assert verifier.verify(BODY, {"X-Hub-Signature-256": signature}) is False
    assert verifier.verify(BODY, {"X-Hub-Signature-256": "sha1=" + signature}) is False


def test_base64_encoding_is_supported() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature", encoding="base64")
    digest = hmac.new(SECRET.encode(), BODY, hashlib.sha256).digest()
    encoded = base64.b64encode(digest).decode()

    assert verifier.verify(BODY, {"X-Signature": encoded}) is True
    assert verifier.verify(BODY, {"X-Signature": encoded[:-4] + "AAAA"}) is False


def test_alternate_algorithm_is_supported() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature", algorithm="sha512")
    expected = hmac.new(SECRET.encode(), BODY, hashlib.sha512).hexdigest()

    assert verifier.verify(BODY, {"X-Signature": expected}) is True
    assert verifier.verify(BODY, {"X-Signature": _hex_signature()}) is False


def test_sign_matches_the_accepted_signature() -> None:
    verifier = HMACSignatureVerifier(SECRET, header="X-Signature")
    assert verifier.sign(BODY) == _hex_signature()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"secret": "", "header": "X-Signature"}, "secret"),
        ({"secret": SECRET, "header": "  "}, "header"),
        ({"secret": SECRET, "header": "X", "algorithm": "rot13"}, "algorithm"),
        ({"secret": SECRET, "header": "X", "encoding": "base32"}, "encoding"),
    ],
)
def test_misconfiguration_fails_loudly(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        HMACSignatureVerifier(**kwargs)
