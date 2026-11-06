"""Drift guards for the hand-written Messenger surfaces (02-3, 02-4, 02-6).

``MessengerPipeline`` restates every ``IMessenger`` signature and forwards the
arguments positionally, and each adapter keeps its ``supported_operations``
by hand. These tests fail CI when either drifts from the contract.
"""

import inspect
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from wappa.connections import IInboxConnector
from wappa.connections.instagram import InstagramConnector
from wappa.connections.whatsapp import WhatsAppConnector
from wappa.core.inbound.platform_webhooks import PlatformWebhooks
from wappa.core.messaging.pipeline import MessengerPipeline
from wappa.core.messaging.pipeline.capabilities import (
    _PipelineTemplates,
    _PipelineUserDataRequests,
)
from wappa.core.messaging.platform_messenger import PlatformMessenger
from wappa.domain.inbox import InboxRef
from wappa.domain.interfaces.media_library import IMediaLibrary
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.interfaces.user_data_requests import (
    USER_DATA_REQUEST_METHODS,
    IUserDataRequests,
)
from wappa.domain.messaging_targets import DeliveryAddresses, DirectMessage
from wappa.domain.results import MessageResult
from wappa.messaging.instagram.media.library import InstagramMediaLibrary
from wappa.messaging.instagram.messenger import InstagramMessengerAdapter
from wappa.messaging.whatsapp.media.library import WhatsAppMediaLibrary
from wappa.messaging.whatsapp.messenger import WhatsAppMessengerAdapter
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.instagram.processor import InstagramWebhookProcessor
from wappa.webhooks.whatsapp.processor import WhatsAppWebhookProcessor

# Every cross-Platform action on the contract: the abstract ones every
# Platform implements plus the optional operations whose base default raises
# UnsupportedOperationError.
OPERATIONS = tuple(
    name
    for name, member in vars(IMessenger).items()
    if inspect.iscoroutinefunction(member) and not name.startswith("_")
)
REQUIRED = frozenset(
    name for name in OPERATIONS if name in IMessenger.__abstractmethods__
)
TEMPLATE_OPERATIONS = tuple(
    name
    for name, member in vars(ITemplateMessaging).items()
    if inspect.iscoroutinefunction(member) and not name.startswith("_")
)
IG_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890001")


def _shape(func: Any) -> list[tuple[str, Any, Any]]:
    """Names, order, kinds and defaults; annotations are strings and may alias."""
    return [
        (p.name, p.kind, p.default) for p in inspect.signature(func).parameters.values()
    ]


def _whatsapp() -> WhatsAppMessengerAdapter:
    return WhatsAppMessengerAdapter(
        client=None,  # type: ignore[arg-type]
        media_transport=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )


def _instagram() -> InstagramMessengerAdapter:
    return InstagramMessengerAdapter(
        inbox_ref=IG_REF,
        access_token=SecretStr("tkn"),
        session_provider=httpx.AsyncClient,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )


def test_operations_list_is_the_contract():
    assert "send_text" in OPERATIONS and "mark_as_read" in OPERATIONS
    assert {"send_text", "resolve_platform_user_profile"} == REQUIRED
    assert set(TEMPLATE_OPERATIONS) == {
        "send_text_template",
        "send_media_template",
        "send_location_template",
    }


@pytest.mark.parametrize("name", OPERATIONS)
def test_pipeline_signature_matches_imessenger(name: str):
    assert _shape(getattr(MessengerPipeline, name)) == _shape(getattr(IMessenger, name))


@pytest.mark.parametrize("name", OPERATIONS)
def test_platform_messenger_signature_matches_imessenger(name: str):
    assert _shape(getattr(PlatformMessenger, name)) == _shape(getattr(IMessenger, name))


@pytest.mark.parametrize("name", TEMPLATE_OPERATIONS)
def test_pipeline_templates_signature_matches_itemplatemessaging(name: str):
    assert _shape(getattr(_PipelineTemplates, name)) == _shape(
        getattr(ITemplateMessaging, name)
    )


@pytest.mark.parametrize(
    "adapter", [WhatsAppMessengerAdapter, InstagramMessengerAdapter]
)
def test_adapter_signatures_match_the_contract(adapter: type[IMessenger]):
    # The pipeline forwards positionally, so the adapter order must match too.
    contracts: list[type] = [IMessenger, ITemplateMessaging]
    for contract in contracts:
        if not issubclass(adapter, contract):
            continue
        for name, member in vars(contract).items():
            if inspect.iscoroutinefunction(member) and not name.startswith("_"):
                assert _shape(getattr(adapter, name)) == _shape(member), name


def test_pipeline_user_data_requests_signature_matches_iuserdatarequests():
    for name in USER_DATA_REQUEST_METHODS:
        assert _shape(getattr(_PipelineUserDataRequests, name)) == _shape(
            getattr(IUserDataRequests, name)
        )
        assert _shape(getattr(WhatsAppMessengerAdapter, name)) == _shape(
            getattr(IUserDataRequests, name)
        )


def _public_methods(contract: type) -> dict[str, Any]:
    return {
        name: member
        for name, member in vars(contract).items()
        if inspect.isfunction(member) and not name.startswith("_")
    }


@pytest.mark.parametrize(
    ("contract", "adapters"),
    [
        (PlatformWebhooks, (WhatsAppWebhookProcessor, InstagramWebhookProcessor)),
        (IMediaLibrary, (WhatsAppMediaLibrary, InstagramMediaLibrary)),
        (IInboxConnector, (WhatsAppConnector, InstagramConnector)),
    ],
    ids=["PlatformWebhooks", "IMediaLibrary", "IInboxConnector"],
)
def test_platform_adapters_match_their_contract_signatures(
    contract: type, adapters: tuple[type, ...]
):
    # Liskov: no extra preconditions and no loosened or dropped parameters.
    methods = _public_methods(contract)
    assert methods, contract
    for adapter in adapters:
        for name, member in methods.items():
            assert _shape(getattr(adapter, name)) == _shape(member), (adapter, name)


@pytest.mark.parametrize("build", [_whatsapp, _instagram])
def test_supported_operations_equal_overridden_methods_plus_qualifiers(build):
    messenger = build()
    overridden = {
        name
        for name in OPERATIONS
        if getattr(type(messenger), name) is not getattr(IMessenger, name)
    }
    qualifiers = {op for op in messenger.supported_operations if ":" in op}
    assert messenger.supported_operations - qualifiers == overridden | REQUIRED
    # A qualifier token (``operation:qualifier``) refines a listed operation.
    for token in qualifiers:
        assert token.split(":", 1)[0] in overridden | REQUIRED, token


class _Recorder(IMessenger, ITemplateMessaging):
    """Raw messenger that records the arguments each call reaches it with."""

    calls: list[tuple[str, dict[str, Any]]]

    def __init__(self) -> None:
        self.calls = []
        self._capabilities = {ITemplateMessaging: self}

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def inbox_id(self) -> str:
        return "pnid"

    async def send_text(self, *args: Any, **kwargs: Any) -> MessageResult:
        return self._record("send_text", IMessenger, args, kwargs)

    def _record(
        self, name: str, contract: type, args: tuple, kwargs: dict
    ) -> MessageResult:
        bound = inspect.signature(getattr(contract, name)).bind(self, *args, **kwargs)
        arguments = dict(bound.arguments)
        arguments.pop("self")
        self.calls.append((name, arguments))
        return MessageResult(success=True, platform=self.platform, inbox_id="pnid")


def _recording(name: str, contract: type):
    async def method(self: _Recorder, *args: Any, **kwargs: Any) -> MessageResult:
        return self._record(name, contract, args, kwargs)

    return method


for _name in OPERATIONS:
    if _name != "send_text":
        setattr(_Recorder, _name, _recording(_name, IMessenger))
for _name in TEMPLATE_OPERATIONS:
    setattr(_Recorder, _name, _recording(_name, ITemplateMessaging))
_Recorder.__abstractmethods__ = frozenset()


def _sentinel_call(func: Any) -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    """One distinct value per parameter, so a swapped position cannot pass."""
    target = DirectMessage(
        inbox_ref=InboxRef.whatsapp("pnid"),
        addresses=DeliveryAddresses.of("573001112233"),
    )
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    expected: dict[str, Any] = {}
    for param in list(inspect.signature(func).parameters.values())[1:]:
        value = target if param.name == "target" else f"<{param.name}>"
        expected[param.name] = value
        if param.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[param.name] = value
        else:
            args.append(value)
    return args, kwargs, expected


@pytest.mark.parametrize("name", OPERATIONS)
async def test_pipeline_forwards_each_argument_under_its_own_name(name: str):
    raw = _Recorder()
    args, kwargs, expected = _sentinel_call(getattr(IMessenger, name))
    await getattr(MessengerPipeline(raw), name)(*args, **kwargs)
    assert raw.calls == [(name, expected)]


@pytest.mark.parametrize("name", OPERATIONS)
async def test_platform_messenger_forwards_each_argument_to_its_messenger(name: str):
    raw = _Recorder()
    args, kwargs, expected = _sentinel_call(getattr(IMessenger, name))
    await getattr(PlatformMessenger(MessengerPipeline(raw)), name)(*args, **kwargs)
    assert raw.calls == [(name, expected)]


@pytest.mark.parametrize("name", TEMPLATE_OPERATIONS)
async def test_pipeline_templates_forward_each_argument_under_its_own_name(name: str):
    raw = _Recorder()
    args, kwargs, expected = _sentinel_call(getattr(ITemplateMessaging, name))
    templates = MessengerPipeline(raw).require_capability(ITemplateMessaging)
    await getattr(templates, name)(*args, **kwargs)
    assert raw.calls == [(name, expected)]


def test_capability_lookup_is_one_base_implementation():
    for adapter in (WhatsAppMessengerAdapter, InstagramMessengerAdapter):
        assert "capability" not in vars(adapter), adapter
        assert "require_capability" not in vars(adapter), adapter


def test_capability_resolves_the_interface_only_on_both():
    wa = _whatsapp()
    library = wa.capability(IMediaLibrary)
    assert isinstance(library, WhatsAppMediaLibrary)
    assert wa.capability(IMediaLibrary) is library  # built once, not per call
    assert wa.capability(WhatsAppMediaLibrary) is None  # never a concrete class
    assert wa.capability(ITemplateMessaging) is wa

    ig = _instagram()
    ig_library = ig.capability(IMediaLibrary)
    assert isinstance(ig_library, InstagramMediaLibrary)
    assert ig.capability(InstagramMediaLibrary) is None
    assert ig.capability(ITemplateMessaging) is None
