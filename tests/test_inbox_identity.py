"""Qualified Inbox and Platform Account identity (PRD 1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wappa.domain.inbox import (
    QUALIFIED_NAMESPACE_SEPARATOR,
    InboxRef,
    PlatformAccountRef,
)
from wappa.persistence import SYSTEM_SCOPE
from wappa.schemas.core.types import PlatformType


def test_same_raw_inbox_id_on_two_platforms_is_two_identities() -> None:
    whatsapp = InboxRef(platform=PlatformType.WHATSAPP, inbox_id="123")
    telegram = InboxRef(platform=PlatformType.TELEGRAM, inbox_id="123")

    assert whatsapp != telegram
    assert hash(whatsapp) != hash(telegram)
    assert whatsapp.cache_namespace != telegram.cache_namespace
    assert len({whatsapp, telegram}) == 2


def test_same_raw_account_id_on_two_platforms_does_not_share_an_index_key() -> None:
    whatsapp = PlatformAccountRef.whatsapp("9001")
    instagram = PlatformAccountRef(
        platform=PlatformType.INSTAGRAM, platform_account_id="9001"
    )

    assert whatsapp != instagram
    assert whatsapp.cache_namespace != instagram.cache_namespace


def test_whatsapp_namespace_is_the_raw_phone_number_id() -> None:
    """Existing WhatsApp Redis keys must stay byte-identical."""
    assert InboxRef.whatsapp("111111111111111").cache_namespace == "111111111111111"


def test_other_platforms_use_a_qualified_namespace() -> None:
    ref = InboxRef(platform=PlatformType.TELEGRAM, inbox_id="123")

    assert ref.cache_namespace == f"telegram{QUALIFIED_NAMESPACE_SEPARATOR}123"


def test_no_inbox_can_encode_to_the_system_scope() -> None:
    with pytest.raises(ValidationError):
        InboxRef.whatsapp(SYSTEM_SCOPE)
    with pytest.raises(ValidationError):
        InboxRef(platform=PlatformType.TELEGRAM, inbox_id="system__")


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "a:b", "a*b", "a?b", "a[b]", "a\\b", "a b", "a__b", "x" * 129, 123],
)
def test_invalid_native_ids_are_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        InboxRef(platform=PlatformType.WHATSAPP, inbox_id=bad)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        PlatformAccountRef(
            platform=PlatformType.WHATSAPP,
            platform_account_id=bad,  # type: ignore[arg-type]
        )


def test_references_are_immutable_and_reject_extra_fields() -> None:
    ref = InboxRef.whatsapp("123")
    with pytest.raises(ValidationError):
        ref.inbox_id = "456"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        InboxRef(platform=PlatformType.WHATSAPP, inbox_id="1", extra="x")  # type: ignore[call-arg]


def test_sorting_orders_platform_before_native_id() -> None:
    refs = [
        InboxRef(platform=PlatformType.TELEGRAM, inbox_id="1"),
        InboxRef.whatsapp("9"),
        InboxRef.whatsapp("10"),
        InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="5"),
    ]

    ordered = sorted(refs)

    assert [r.sort_key for r in ordered] == [
        ("instagram", "5"),
        ("telegram", "1"),
        ("whatsapp", "10"),
        ("whatsapp", "9"),
    ]
    assert sorted({InboxRef.whatsapp("2"), InboxRef.whatsapp("1")}) == [
        InboxRef.whatsapp("1"),
        InboxRef.whatsapp("2"),
    ]


def test_serialization_is_deterministic() -> None:
    ref = InboxRef.whatsapp("123")
    account = PlatformAccountRef.whatsapp("9001")

    assert ref.model_dump(mode="json") == {"platform": "whatsapp", "inbox_id": "123"}
    assert InboxRef.model_validate(ref.model_dump(mode="json")) == ref
    assert account.model_dump(mode="json") == {
        "platform": "whatsapp",
        "platform_account_id": "9001",
    }
    assert str(ref) == "whatsapp:123"
    assert str(account) == "whatsapp:9001"
