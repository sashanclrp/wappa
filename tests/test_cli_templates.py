"""The scaffolded `wappa init` code compiles and its handler sends a valid target."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from wappa.domain.inbox import InboxRef
from wappa.domain.messaging_targets import DeliveryAddresses, DirectMessage
from wappa.schemas.core.types import PlatformType

TEMPLATES = Path(__file__).resolve().parents[1] / "wappa" / "cli" / "templates"


@pytest.mark.parametrize(
    "template", sorted(TEMPLATES.glob("*.py.template")), ids=lambda p: p.name
)
def test_python_template_compiles(template: Path) -> None:
    compile(template.read_text(), str(template), "exec")


class _RecordingMessenger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def mark_as_read(self, *args, **kwargs):
        self.calls.append(("mark_as_read", args, kwargs))

    async def send_text(self, *args, **kwargs):
        self.calls.append(("send_text", args, kwargs))


async def test_master_event_template_replies_to_a_direct_message() -> None:
    namespace: dict = {}
    source = (TEMPLATES / "master_event.py.template").read_text()
    exec(compile(source, "master_event.py", "exec"), namespace)

    handler = namespace["MasterEventHandler"]()
    inbox_ref = InboxRef(platform=PlatformType.WHATSAPP, inbox_id="123")
    handler.inbox_ref = inbox_ref
    handler.messenger = _RecordingMessenger()
    webhook = SimpleNamespace(
        message=SimpleNamespace(message_id="wamid.1"),
        user=SimpleNamespace(
            delivery_addresses=lambda: DeliveryAddresses(values=("573000000000",))
        ),
    )

    await handler.process_message(webhook)

    (_, read_args, _), (_, send_args, _) = handler.messenger.calls
    target = send_args[1]
    assert isinstance(target, DirectMessage)
    assert target.inbox_ref == inbox_ref
    assert read_args == ("wamid.1", target)
