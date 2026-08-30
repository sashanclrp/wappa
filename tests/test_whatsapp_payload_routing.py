"""Qualified WhatsApp payload routing with WABA membership (PRD 3)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from wappa.core.inbound import (
    PayloadRoutingError,
    PlatformAccountNotRegisteredError,
    route_whatsapp_payload,
)
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    InboxDirectoryUnavailableError,
    InboxMembershipError,
    InboxNotFoundError,
    InboxRef,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)
from wappa.schemas.core.types import PlatformType

WABA_1 = PlatformAccountRef.whatsapp("waba-1")
WABA_2 = PlatformAccountRef.whatsapp("waba-2")


class _Resolver(IInboxCredentialResolver):
    def __init__(self) -> None:
        self.inboxes: dict[InboxRef, PlatformAccountRef] = {
            InboxRef.whatsapp("phone-1"): WABA_1,
            InboxRef.whatsapp("phone-2"): WABA_1,
            InboxRef.whatsapp("phone-3"): WABA_2,
        }
        self.members: dict[PlatformAccountRef, tuple[InboxRef, ...]] = {
            WABA_1: (
                InboxRef.whatsapp("phone-2"),
                InboxRef.whatsapp("phone-1"),
                InboxRef.whatsapp("phone-2"),
            ),
        }
        self.unavailable = False
        self.resolve_calls: list[InboxRef] = []

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        self.resolve_calls.append(inbox_ref)
        if self.unavailable:
            raise InboxDirectoryUnavailableError("directory down")
        account = self.inboxes.get(inbox_ref)
        if account is None:
            raise InboxNotFoundError(inbox_ref)
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=account,
            access_token=SecretStr(f"token-{inbox_ref.inbox_id}"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        if self.unavailable:
            raise InboxDirectoryUnavailableError("directory down")
        return self.members.get(account_ref, ())


def _payload(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"object": "whatsapp_business_account", "entry": list(entries)}


def _entry(waba_id: str, *values: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": waba_id,
        "changes": [
            {"field": f"field-{index}", "value": value}
            for index, value in enumerate(values)
        ],
    }


async def test_metadata_phone_number_id_is_the_inbox_and_carries_credentials() -> None:
    deliveries = await route_whatsapp_payload(
        _payload(_entry("waba-2", {"metadata": {"phone_number_id": "phone-3"}})),
        _Resolver(),
    )

    (delivery,) = deliveries
    assert delivery.inbox_ref == InboxRef.whatsapp("phone-3")
    assert delivery.account_ref == WABA_2
    assert delivery.credentials.access_token.get_secret_value() == "token-phone-3"
    assert delivery.inbox_id == "phone-3"


async def test_flat_phone_number_id_is_the_inbox() -> None:
    deliveries = await route_whatsapp_payload(
        _payload(_entry("waba-1", {"phone_number_id": "phone-1"})), _Resolver()
    )

    assert [d.inbox_ref for d in deliveries] == [InboxRef.whatsapp("phone-1")]


async def test_two_phone_scoped_changes_under_one_waba_route_to_distinct_inboxes() -> (
    None
):
    deliveries = await route_whatsapp_payload(
        _payload(
            _entry(
                "waba-1",
                {"metadata": {"phone_number_id": "phone-1"}},
                {"metadata": {"phone_number_id": "phone-2"}},
            )
        ),
        _Resolver(),
    )

    assert [d.inbox_id for d in deliveries] == ["phone-1", "phone-2"]
    assert {d.credentials.access_token.get_secret_value() for d in deliveries} == {
        "token-phone-1",
        "token-phone-2",
    }


async def test_phone_scoped_change_must_belong_to_the_entry_waba() -> None:
    with pytest.raises(InboxMembershipError):
        await route_whatsapp_payload(
            _payload(_entry("waba-2", {"metadata": {"phone_number_id": "phone-1"}})),
            _Resolver(),
        )


async def test_unknown_phone_inbox_is_not_found() -> None:
    with pytest.raises(InboxNotFoundError):
        await route_whatsapp_payload(
            _payload(_entry("waba-1", {"metadata": {"phone_number_id": "phone-9"}})),
            _Resolver(),
        )


async def test_invalid_phone_number_id_format_is_a_routing_error() -> None:
    with pytest.raises(PayloadRoutingError, match="not a valid Inbox identifier"):
        await route_whatsapp_payload(
            _payload(_entry("waba-1", {"metadata": {"phone_number_id": "a:b"}})),
            _Resolver(),
        )


async def test_waba_scoped_change_fans_out_sorted_and_deduplicated() -> None:
    resolver = _Resolver()

    deliveries = await route_whatsapp_payload(
        _payload(_entry("waba-1", {"reason": "account scoped"})), resolver
    )

    assert [d.inbox_id for d in deliveries] == ["phone-1", "phone-2"]
    assert all(d.account_ref == WABA_1 for d in deliveries)
    assert all(d.payload["entry"][0]["id"] == "waba-1" for d in deliveries)
    assert resolver.resolve_calls == [
        InboxRef.whatsapp("phone-1"),
        InboxRef.whatsapp("phone-2"),
    ]


async def test_confirmed_empty_waba_fails_closed() -> None:
    with pytest.raises(PlatformAccountNotRegisteredError, match="waba-2"):
        await route_whatsapp_payload(
            _payload(_entry("waba-2", {"account_scope": True})), _Resolver()
        )


async def test_entry_id_is_never_used_as_an_inbox_fallback() -> None:
    resolver = _Resolver()
    resolver.inboxes[InboxRef.whatsapp("waba-missing")] = WABA_1

    with pytest.raises(PlatformAccountNotRegisteredError):
        await route_whatsapp_payload(
            _payload(_entry("waba-missing", {"account_scope": True})), resolver
        )
    assert resolver.resolve_calls == []


async def test_fan_out_member_that_moved_to_another_waba_is_a_membership_error() -> (
    None
):
    resolver = _Resolver()
    resolver.inboxes[InboxRef.whatsapp("phone-2")] = WABA_2

    with pytest.raises(InboxMembershipError):
        await route_whatsapp_payload(
            _payload(_entry("waba-1", {"account_scope": True})), resolver
        )


async def test_same_raw_inbox_id_on_another_platform_cannot_satisfy_whatsapp() -> None:
    resolver = _Resolver()
    resolver.inboxes = {
        InboxRef(
            platform=PlatformType.TELEGRAM, inbox_id="phone-1"
        ): PlatformAccountRef(
            platform=PlatformType.TELEGRAM, platform_account_id="waba-1"
        )
    }

    with pytest.raises(InboxNotFoundError):
        await route_whatsapp_payload(
            _payload(_entry("waba-1", {"metadata": {"phone_number_id": "phone-1"}})),
            resolver,
        )


async def test_directory_outage_propagates_as_unavailable() -> None:
    resolver = _Resolver()
    resolver.unavailable = True

    with pytest.raises(InboxDirectoryUnavailableError):
        await route_whatsapp_payload(
            _payload(_entry("waba-1", {"metadata": {"phone_number_id": "phone-1"}})),
            resolver,
        )
    with pytest.raises(InboxDirectoryUnavailableError):
        await route_whatsapp_payload(
            _payload(_entry("waba-1", {"account_scope": True})), resolver
        )


async def test_batched_changes_split_in_entry_and_change_order() -> None:
    deliveries = await route_whatsapp_payload(
        _payload(
            _entry(
                "waba-1",
                {"metadata": {"phone_number_id": "phone-1"}},
                {"account_scope": True},
            ),
            _entry("waba-2", {"phone_number_id": "phone-3"}),
        ),
        _Resolver(),
    )

    assert [d.inbox_id for d in deliveries] == [
        "phone-1",
        "phone-1",
        "phone-2",
        "phone-3",
    ]
    assert all(len(d.payload["entry"]) == 1 for d in deliveries)
    assert all(len(d.payload["entry"][0]["changes"]) == 1 for d in deliveries)


async def test_flat_waba_id_must_match_entry_id() -> None:
    with pytest.raises(PayloadRoutingError, match="WABA mismatch"):
        await route_whatsapp_payload(
            _payload(
                _entry("waba-1", {"waba_id": "waba-2", "phone_number_id": "phone-1"})
            ),
            _Resolver(),
        )


async def test_metadata_and_flat_phone_number_ids_cannot_conflict() -> None:
    with pytest.raises(PayloadRoutingError, match="conflicting"):
        await route_whatsapp_payload(
            _payload(
                _entry(
                    "waba-1",
                    {
                        "metadata": {"phone_number_id": "phone-1"},
                        "phone_number_id": "phone-2",
                    },
                )
            ),
            _Resolver(),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"object": "page", "entry": []},
        {"object": "whatsapp_business_account"},
        {"object": "whatsapp_business_account", "entry": []},
        {"object": "whatsapp_business_account", "entry": ["x"]},
        {"object": "whatsapp_business_account", "entry": [{"id": "", "changes": []}]},
        {"object": "whatsapp_business_account", "entry": [{"id": "w", "changes": []}]},
        {"object": "whatsapp_business_account", "entry": [{"id": "w", "changes": [1]}]},
        {
            "object": "whatsapp_business_account",
            "entry": [{"id": "w", "changes": [{"value": 1}]}],
        },
        {
            "object": "whatsapp_business_account",
            "entry": [{"id": "a:b", "changes": [{"value": {}}]}],
        },
    ],
)
async def test_structurally_unroutable_payloads_are_routing_errors(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(PayloadRoutingError):
        await route_whatsapp_payload(payload, _Resolver())
