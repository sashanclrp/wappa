"""Legacy/explicit Inbox Routing Modes and Meta configuration sources (PRD 4)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from wappa.core.config.meta_application import (
    MetaApplicationConfig,
    resolve_meta_application_config,
)
from wappa.core.config.settings import settings
from wappa.core.factory.inbox_assembly import (
    assemble_inbox_runtime,
    resolve_routing_mode,
)
from wappa.core.factory.wappa_builder import WappaBuilder
from wappa.core.plugins.wappa_core_plugin import WappaCorePlugin
from wappa.core.security import CredentialCodec
from wappa.core.wappa_app import Wappa
from wappa.domain.inbox import (
    InboxConfigurationError,
    InboxDirectory,
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
    SettingsInboxCredentialResolver,
)
from wappa.webhooks import InboundMessageWebhook


class _Source:
    async def get_inbox(self, inbox_ref: InboxRef) -> Any:
        return None

    async def list_inboxes_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[Any, ...]:
        return ()


class _NotASource:
    pass


@pytest.fixture
def legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "wp_access_token", "legacy-access-token-value")
    monkeypatch.setattr(settings, "wp_phone_id", "111")
    monkeypatch.setattr(settings, "wp_bid", "9001")
    monkeypatch.setattr(settings, "inbox_routing_mode", None)
    monkeypatch.setattr(settings, "system_token_enc_key", None)
    monkeypatch.setattr(settings, "system_token_enc_previous_keys", None)


@pytest.fixture
def explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "wp_access_token", None)
    monkeypatch.setattr(settings, "wp_phone_id", None)
    monkeypatch.setattr(settings, "wp_bid", None)
    monkeypatch.setattr(settings, "inbox_routing_mode", None)
    monkeypatch.setattr(
        settings, "system_token_enc_key", CredentialCodec.generate_key()
    )
    monkeypatch.setattr(settings, "system_token_enc_previous_keys", None)


@pytest.fixture
def callback_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "meta_app_secret", "app-secret-value")
    monkeypatch.setattr(settings, "wp_webhook_verify_token", "verify-token-value")


# ── mode resolution ─────────────────────────────────────────────────────────


def test_omitted_mode_defaults_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "inbox_routing_mode", None)
    assert resolve_routing_mode(None, settings) is InboxRoutingMode.LEGACY


def test_environment_mode_is_honoured_and_builder_argument_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "inbox_routing_mode", "explicit")
    assert resolve_routing_mode(None, settings) is InboxRoutingMode.EXPLICIT
    assert resolve_routing_mode("legacy", settings) is InboxRoutingMode.LEGACY
    assert (
        resolve_routing_mode(InboxRoutingMode.EXPLICIT, settings)
        is InboxRoutingMode.EXPLICIT
    )


@pytest.mark.parametrize("bad", ["auto", "default", "", "hybrid"])
def test_there_is_no_third_mode(bad: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "inbox_routing_mode", None)
    if bad == "":
        monkeypatch.setattr(settings, "inbox_routing_mode", bad)
        assert resolve_routing_mode(None, settings) is InboxRoutingMode.LEGACY
        return
    with pytest.raises(InboxConfigurationError):
        resolve_routing_mode(bad, settings)
    assert {m.value for m in InboxRoutingMode} == {"legacy", "explicit"}


# ── legacy mode ─────────────────────────────────────────────────────────────


def test_legacy_mode_requires_the_complete_bundle_and_has_one_default(
    legacy_env: None,
) -> None:
    runtime = assemble_inbox_runtime(
        mode=InboxRoutingMode.LEGACY,
        source=None,
        settings=settings,
        cache_type="memory",
    )

    assert runtime.mode is InboxRoutingMode.LEGACY
    assert isinstance(runtime.credential_resolver, SettingsInboxCredentialResolver)
    assert runtime.default_inbox_ref == InboxRef.whatsapp("111")
    assert runtime.directory is None
    assert runtime.health_status()["legacy_default_inbox_id"] == "111"


@pytest.mark.parametrize("missing", ["wp_access_token", "wp_phone_id", "wp_bid"])
def test_legacy_mode_rejects_a_partial_bundle(
    legacy_env: None, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setattr(settings, missing, None)

    with pytest.raises(InboxConfigurationError, match="complete bundle"):
        assemble_inbox_runtime(
            mode=InboxRoutingMode.LEGACY,
            source=None,
            settings=settings,
            cache_type="memory",
        )


def test_legacy_mode_rejects_a_directory_source(legacy_env: None) -> None:
    with pytest.raises(
        InboxConfigurationError, match="rejects an IInboxDirectorySource"
    ):
        assemble_inbox_runtime(
            mode=InboxRoutingMode.LEGACY,
            source=_Source(),
            settings=settings,
            cache_type="memory",
        )


def test_source_without_explicit_mode_fails_at_build(legacy_env: None) -> None:
    with pytest.raises(
        InboxConfigurationError, match="rejects an IInboxDirectorySource"
    ):
        WappaBuilder().with_inbox_directory_source(_Source()).build()


async def test_legacy_resolver_only_knows_its_one_inbox(legacy_env: None) -> None:
    runtime = assemble_inbox_runtime(
        mode=InboxRoutingMode.LEGACY,
        source=None,
        settings=settings,
        cache_type="memory",
    )
    resolver = runtime.credential_resolver

    credentials = await resolver.resolve_credentials(InboxRef.whatsapp("111"))
    assert credentials.access_token.get_secret_value() == "legacy-access-token-value"
    assert credentials.account_ref == PlatformAccountRef.whatsapp("9001")
    assert await resolver.list_inbox_refs_for_platform_account(
        PlatformAccountRef.whatsapp("9001")
    ) == (InboxRef.whatsapp("111"),)
    assert (
        await resolver.list_inbox_refs_for_platform_account(
            PlatformAccountRef.whatsapp("other")
        )
        == ()
    )
    from wappa.domain.inbox import InboxNotFoundError

    with pytest.raises(InboxNotFoundError):
        await resolver.resolve_credentials(InboxRef.whatsapp("222"))


# ── explicit mode ───────────────────────────────────────────────────────────


def test_explicit_mode_builds_the_directory_and_has_no_default(
    explicit_env: None,
) -> None:
    runtime = assemble_inbox_runtime(
        mode=InboxRoutingMode.EXPLICIT,
        source=_Source(),
        settings=settings,
        cache_type="memory",
    )

    assert runtime.mode is InboxRoutingMode.EXPLICIT
    assert isinstance(runtime.directory, InboxDirectory)
    assert runtime.credential_resolver is runtime.directory
    assert runtime.default_inbox_ref is None
    assert runtime.credential_service is not None
    assert runtime.health_status()["inbox_directory_configured"] is True


def test_explicit_mode_requires_a_source(explicit_env: None) -> None:
    with pytest.raises(
        InboxConfigurationError, match="requires an IInboxDirectorySource"
    ):
        assemble_inbox_runtime(
            mode=InboxRoutingMode.EXPLICIT,
            source=None,
            settings=settings,
            cache_type="memory",
        )


def test_explicit_mode_rejects_an_object_that_is_not_a_source(
    explicit_env: None,
) -> None:
    with pytest.raises(InboxConfigurationError, match="must implement"):
        assemble_inbox_runtime(
            mode=InboxRoutingMode.EXPLICIT,
            source=_NotASource(),  # type: ignore[arg-type]
            settings=settings,
            cache_type="memory",
        )


@pytest.mark.parametrize("leftover", ["wp_access_token", "wp_phone_id", "wp_bid"])
def test_explicit_mode_rejects_every_legacy_variable(
    explicit_env: None, monkeypatch: pytest.MonkeyPatch, leftover: str
) -> None:
    monkeypatch.setattr(settings, leftover, "leftover")

    with pytest.raises(
        InboxConfigurationError, match="rejects the legacy Inbox variables"
    ):
        assemble_inbox_runtime(
            mode=InboxRoutingMode.EXPLICIT,
            source=_Source(),
            settings=settings,
            cache_type="memory",
        )


@pytest.mark.parametrize("key", [None, "", "not-a-fernet-key"])
def test_explicit_mode_rejects_a_missing_or_malformed_encryption_key(
    explicit_env: None, monkeypatch: pytest.MonkeyPatch, key: str | None
) -> None:
    monkeypatch.setattr(settings, "system_token_enc_key", key)

    with pytest.raises(InboxConfigurationError) as exc_info:
        assemble_inbox_runtime(
            mode=InboxRoutingMode.EXPLICIT,
            source=_Source(),
            settings=settings,
            cache_type="memory",
        )
    assert "SYSTEM_TOKEN_ENC_KEY" in str(exc_info.value)
    if key:
        assert key not in str(exc_info.value)


def test_explicit_mode_accepts_a_previous_key_ring(
    explicit_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        settings,
        "system_token_enc_previous_keys",
        f"{CredentialCodec.generate_key()},{CredentialCodec.generate_key()}",
    )

    runtime = assemble_inbox_runtime(
        mode=InboxRoutingMode.EXPLICIT,
        source=_Source(),
        settings=settings,
        cache_type="memory",
    )
    assert runtime.directory is not None


def test_builder_and_wappa_expose_explicit_mode(explicit_env: None) -> None:
    app = (
        WappaBuilder()
        .with_inbox_routing("explicit")
        .with_inbox_directory_source(_Source())
        .build()
    )
    assert app.state.inbox_routing_mode is InboxRoutingMode.EXPLICIT
    assert app.state.inbox_runtime.default_inbox_ref is None

    wappa = Wappa(
        inbox_directory_source=_Source(), inbox_routing=InboxRoutingMode.EXPLICIT
    )
    assert wappa._builder.inbox_routing_mode is InboxRoutingMode.EXPLICIT
    assert wappa._builder.inbox_directory_source is not None


def test_builder_wires_legacy_mode_by_default(legacy_env: None) -> None:
    app = WappaBuilder().build()

    assert app.state.inbox_routing_mode is InboxRoutingMode.LEGACY
    assert app.state.inbox_runtime.default_inbox_ref == InboxRef.whatsapp("111")


# ── Meta Application Configuration ─────────────────────────────────────────


def test_environment_meta_configuration_is_built_when_mounted(
    callback_env: None,
) -> None:
    config = resolve_meta_application_config(None, settings, callback_mounted=True)

    assert config is not None
    assert config.app_secret.get_secret_value() == "app-secret-value"
    assert (
        config.whatsapp_webhook_verify_token.get_secret_value() == "verify-token-value"
    )
    assert config.graph_api_version == settings.api_version
    assert "app-secret-value" not in repr(config)
    assert "verify-token-value" not in repr(config)
    assert config.health_status() == {
        "app_secret_configured": True,
        "verify_token_configured": True,
        "graph_api_version": settings.api_version,
        "graph_base_url": str(config.graph_base_url),
    }


def test_explicit_and_environment_meta_configuration_cannot_coexist(
    callback_env: None,
) -> None:
    explicit = MetaApplicationConfig(
        app_secret=SecretStr("x"), whatsapp_webhook_verify_token=SecretStr("y")
    )

    with pytest.raises(InboxConfigurationError, match="exactly one"):
        resolve_meta_application_config(explicit, settings, callback_mounted=True)


def test_explicit_meta_configuration_alone_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "meta_app_secret", None)
    monkeypatch.setattr(settings, "wp_webhook_verify_token", None)
    explicit = MetaApplicationConfig(
        app_secret=SecretStr("x"), whatsapp_webhook_verify_token=SecretStr("y")
    )

    assert (
        resolve_meta_application_config(explicit, settings, callback_mounted=True)
        is explicit
    )


@pytest.mark.parametrize("missing", ["meta_app_secret", "wp_webhook_verify_token"])
def test_mounted_callback_requires_both_secrets(
    callback_env: None, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setattr(settings, missing, None)

    with pytest.raises(InboxConfigurationError, match="required"):
        resolve_meta_application_config(None, settings, callback_mounted=True)


def test_outbound_only_application_needs_no_callback_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "meta_app_secret", None)
    monkeypatch.setattr(settings, "wp_webhook_verify_token", None)

    assert (
        resolve_meta_application_config(None, settings, callback_mounted=False) is None
    )


def test_mounting_the_callback_without_secrets_fails_startup(
    legacy_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "meta_app_secret", None)
    monkeypatch.setattr(settings, "wp_webhook_verify_token", None)

    class _Handler(
        InboundMessageWebhook.__mro__[0] if False else object
    ):  # pragma: no cover
        pass

    from wappa.core.events.event_handler import WappaEventHandler

    class _Noop(WappaEventHandler):
        async def process_message(self, webhook: InboundMessageWebhook) -> None:
            return None

    wappa = Wappa()
    wappa.set_event_handler(_Noop())
    with pytest.raises(InboxConfigurationError, match="no development bypass"):
        _ = wappa.asgi


def test_there_is_no_meta_application_secret_in_inbox_records(
    callback_env: None,
) -> None:
    from wappa.domain.inbox import WhatsAppActiveInboxCredentialRecord

    assert "app_secret" not in WhatsAppActiveInboxCredentialRecord.model_fields


# ── health ──────────────────────────────────────────────────────────────────


def _health_app(legacy: bool) -> FastAPI:
    from wappa.api.routes.health import router as health_router

    app = FastAPI()
    if legacy:
        app.state.inbox_runtime = assemble_inbox_runtime(
            mode=InboxRoutingMode.LEGACY,
            source=None,
            settings=settings,
            cache_type="memory",
        )
    else:
        app.state.inbox_runtime = assemble_inbox_runtime(
            mode=InboxRoutingMode.EXPLICIT,
            source=_Source(),
            settings=settings,
            cache_type="memory",
        )
    app.state.meta_application_config = MetaApplicationConfig(
        app_secret=SecretStr("app-secret"),
        whatsapp_webhook_verify_token=SecretStr("verify"),
    )
    app.include_router(health_router)
    return app


def test_health_reports_legacy_mode_and_redacts_the_token(legacy_env: None) -> None:
    client = TestClient(_health_app(legacy=True))

    basic = client.get("/health").json()
    detailed = client.get("/health/detailed").json()

    assert basic["environment"]["inbox_routing_mode"] == "legacy"
    assert basic["environment"]["legacy_default_inbox_id"] == "111"
    whatsapp = detailed["platform_configs"]["whatsapp"]
    assert whatsapp["inbox_routing_mode"] == "legacy"
    assert whatsapp["legacy_default_inbox"] == {"configured": True, "inbox_id": "111"}
    assert whatsapp["meta_callback"]["configured"] is True
    assert "legacy-access-token-value" not in str(detailed)
    assert "app-secret-value" not in str(detailed)
    assert "verify-token-value" not in str(detailed)


def test_health_reports_explicit_mode_and_directory_reachability(
    explicit_env: None,
) -> None:
    client = TestClient(_health_app(legacy=False))

    detailed = client.get("/health/detailed").json()

    whatsapp = detailed["platform_configs"]["whatsapp"]
    assert whatsapp["inbox_routing_mode"] == "explicit"
    assert whatsapp["inbox_directory"] == {
        "configured": True,
        "reachability": "reachable",
    }
    assert whatsapp["legacy_default_inbox"] == {"configured": False, "inbox_id": None}
    assert settings.system_token_enc_key not in str(detailed)


def test_root_health_needs_no_inbox_header(explicit_env: None) -> None:
    app = _health_app(legacy=False)
    app.add_middleware(
        __import__("wappa.api.middleware", fromlist=["InboxMiddleware"]).InboxMiddleware
    )
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert (
        client.get("/health", headers={"X-Wappa-Inbox-ID": "nope"}).status_code == 200
    )


async def test_core_plugin_startup_logs_the_mode_and_needs_no_legacy_lookup(
    explicit_env: None,
) -> None:
    app = FastAPI()
    app.state.inbox_runtime = assemble_inbox_runtime(
        mode=InboxRoutingMode.EXPLICIT,
        source=_Source(),
        settings=settings,
        cache_type="memory",
    )
    app.state.meta_application_config = None
    plugin = WappaCorePlugin()

    await plugin._core_startup(app)
    try:
        assert app.state.session_lifecycle is not None
    finally:
        await plugin._core_shutdown(app)
