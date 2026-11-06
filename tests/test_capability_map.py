"""Each adapter's capabilities are exactly the ADR-0025 contract map.

The map is parsed from the "Contract map" table in
``docs/adr/0025-messenger-contract.md``: every capability row names its
interfaces in backticks (``(later ...)`` entries are not built yet), and a
Platform column starting with "—" means that Platform does not provide it.
Adding or removing a capability therefore means updating the ADR too.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from wappa.domain.inbox import InboxRef
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.instagram.messenger import InstagramMessengerAdapter
from wappa.messaging.whatsapp.messenger import WhatsAppMessengerAdapter
from wappa.schemas.core.types import PlatformType

ADR = Path(__file__).resolve().parents[1] / "docs/adr/0025-messenger-contract.md"


def _adr_capability_map() -> dict[str, set[str]]:
    text = ADR.read_text()
    table = text.split("## Contract map", 1)[1].split("\n\n", 2)[1]
    rows = [line for line in table.splitlines() if line.startswith("|")]
    header = [cell.strip() for cell in rows[0].strip("|").split("|")]
    columns = {name: header.index(name) for name in ("WhatsApp", "Instagram")}
    found: dict[str, set[str]] = {name: set() for name in columns}
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if "capability" not in cells[0].lower():
            continue
        contract = re.sub(r"\(later[^)]*\)", "", cells[1])
        interfaces = set(re.findall(r"`(I[A-Z]\w+)`", contract))
        for platform, index in columns.items():
            if not cells[index].startswith("—"):
                found[platform] |= interfaces
    return found


def _whatsapp() -> IMessenger:
    return WhatsAppMessengerAdapter(
        client=None,  # type: ignore[arg-type]
        media_transport=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )


def _instagram() -> IMessenger:
    return InstagramMessengerAdapter(
        inbox_ref=InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001"),
        access_token=SecretStr("tkn"),
        session_provider=httpx.AsyncClient,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )


def test_the_adr_map_parses() -> None:
    adr = _adr_capability_map()
    assert "IMediaLibrary" in adr["WhatsApp"] & adr["Instagram"]
    assert "ITemplateMessaging" in adr["WhatsApp"] - adr["Instagram"]


@pytest.mark.parametrize(
    ("column", "build"),
    [("WhatsApp", _whatsapp), ("Instagram", _instagram)],
    ids=["whatsapp", "instagram"],
)
def test_adapter_capabilities_match_the_adr_contract_map(column, build) -> None:
    messenger = build()
    registered = {kind.__name__ for kind in messenger._capabilities}
    assert registered == _adr_capability_map()[column]
    for kind in messenger._capabilities:
        assert messenger.capability(kind) is not None, kind
