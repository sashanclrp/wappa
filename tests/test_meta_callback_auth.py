"""Raw-body Meta callback authentication (PRD 3)."""

from __future__ import annotations

import hashlib
import hmac

import pytest
from pydantic import SecretStr

from wappa.core.inbound import SIGNATURE_HEADER, MetaCallbackAuthenticator

SECRET = SecretStr("meta-app-secret")
BODY = b'{"object":"whatsapp_business_account","entry":[]}'


def _hex(body: bytes = BODY, secret: str = "meta-app-secret") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_header_name_is_metas() -> None:
    assert SIGNATURE_HEADER == "X-Hub-Signature-256"


def test_valid_signature_is_accepted() -> None:
    auth = MetaCallbackAuthenticator(SECRET)
    assert auth.verify(BODY, f"sha256={_hex()}") is True
    assert auth.verify(BODY, auth.sign(BODY)) is True


def test_exact_bytes_including_whitespace_are_the_hmac_input() -> None:
    auth = MetaCallbackAuthenticator(SECRET)
    spaced = b'{"object": "whatsapp_business_account", "entry": []}'

    assert auth.verify(spaced, auth.sign(spaced)) is True
    assert auth.verify(spaced, auth.sign(BODY)) is False
    assert auth.verify(BODY + b"\n", auth.sign(BODY)) is False


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        _hex(),
        f"sha1={_hex()}",
        f"sha256={_hex()[:-2]}",
        f"sha256={_hex()}00",
        "sha256=" + "zz" * 32,
        f"sha256={_hex(secret='other-secret')}",
        f"sha256={_hex(body=b'{}')}",
    ],
)
def test_missing_malformed_and_mismatched_signatures_are_all_rejected(
    header: str | None,
) -> None:
    assert MetaCallbackAuthenticator(SECRET).verify(BODY, header) is False


def test_hex_case_does_not_change_the_verdict() -> None:
    auth = MetaCallbackAuthenticator(SECRET)
    assert auth.verify(BODY, f"sha256={_hex().upper()}") is True


def test_empty_app_secret_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError):
        MetaCallbackAuthenticator(SecretStr(""))
