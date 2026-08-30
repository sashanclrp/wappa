"""Inbox Execution Context and the WhatsApp route capability matrix (PRDs 4 and 5)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from wappa.api.dependencies.inbox_context import (
    INBOX_ID_HEADER,
    InboxExecutionContext,
    get_inbox_execution_context,
)
from wappa.api.middleware import InboxMiddleware
from wappa.api.routes.whatsapp_combined import create_whatsapp_router
from wappa.core.auth.middleware import AuthMiddleware
from wappa.core.auth.strategies.bearer_token import BearerTokenStrategy
from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.core.logging.context import get_current_inbox_context
from wappa.domain.inbox import (
    IInboxCredentialResolver,
    InboxCredentialIntegrityError,
    InboxDirectoryUnavailableError,
    InboxNotFoundError,
    InboxRef,
    InboxRoutingMode,
    PlatformAccountRef,
    ResolvedInboxCredentials,
)

INBOX_A = "111111111111111"
INBOX_B = "222222222222222"


class _Resolver(IInboxCredentialResolver):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failure: Exception | None = None
        self.inboxes = {INBOX_A: "waba-a", INBOX_B: "waba-b"}

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        self.calls.append(inbox_ref.inbox_id)
        if self.failure is not None:
            raise self.failure
        waba = self.inboxes.get(inbox_ref.inbox_id)
        if waba is None:
            raise InboxNotFoundError(inbox_ref)
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=PlatformAccountRef.whatsapp(waba),
            access_token=SecretStr(f"token-{inbox_ref.inbox_id}"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        return ()


class _RecordingSession:
    """Answers Meta calls so Inbox-dependent routes complete."""

    is_closed = False

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def get(
        self, url: str, *, headers: dict[str, str], params: Any = None
    ) -> httpx.Response:
        self.requests.append({"url": url, "headers": headers, "params": params})
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        if "message_template_namespace" in str(params) or tail.startswith("waba-"):
            payload: dict[str, Any] = {"message_template_namespace": "ns", "id": tail}
        elif tail == "message_templates":
            payload = {"data": [], "paging": {}}
        elif tail == "42":
            payload = {
                "id": "42",
                "name": "welcome",
                "status": "APPROVED",
                "category": "UTILITY",
                "language": "en",
            }
        else:
            payload = {
                "url": "https://cdn.example/media",
                "mime_type": "image/jpeg",
                "sha256": "x",
                "file_size": 3,
                "id": tail,
            }
        return httpx.Response(200, request=httpx.Request("GET", url), json=payload)

    async def delete(
        self, url: str, *, headers: dict[str, str], params: Any = None
    ) -> httpx.Response:
        self.requests.append({"url": url, "headers": headers, "params": params})
        return httpx.Response(
            200, request=httpx.Request("DELETE", url), json={"success": True}
        )

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: Any = None,
        data: Any = None,
        files: Any = None,
    ) -> httpx.Response:
        self.requests.append({"url": url, "headers": headers, "payload": json or data})
        if url.rstrip("/").endswith("/media"):
            payload: dict[str, Any] = {"id": "media-1"}
        else:
            payload = {
                "messaging_product": "whatsapp",
                "contacts": [{"input": "1", "wa_id": "1"}],
                "messages": [{"id": "wamid.1"}],
            }
        return httpx.Response(200, request=httpx.Request("POST", url), json=payload)

    def stream(self, method: str, url: str, **kwargs: Any) -> Any:
        session = self

        class _Response:
            status_code = 200
            headers = {"content-type": "image/jpeg", "content-length": "3"}

            async def aiter_bytes(self, chunk_size: int = 1024) -> Any:
                yield b"abc"

            async def aread(self) -> bytes:
                return b"abc"

            def raise_for_status(self) -> None:
                return None

        class _Stream:
            async def __aenter__(self) -> Any:
                session.requests.append(
                    {"url": url, "headers": kwargs.get("headers", {}), "stream": True}
                )
                return _Response()

            async def __aexit__(self, *exc: Any) -> None:
                return None

        return _Stream()


def _app(
    resolver: _Resolver, *, mode: InboxRoutingMode, auth: bool = False
) -> tuple[FastAPI, _RecordingSession]:
    app = FastAPI()
    session = _RecordingSession()
    app.state.session_lifecycle = SessionLifecycle(session)  # type: ignore[arg-type]
    app.state.background_work_tracker = BackgroundWorkTracker()
    app.state.wappa_cache_type = "memory"
    app.state.messenger_middleware = []
    app.state.inbox_runtime = InboxRuntimeConfiguration(
        mode=mode,
        credential_resolver=resolver,
        default_inbox_ref=InboxRef.whatsapp(INBOX_A)
        if mode is InboxRoutingMode.LEGACY
        else None,
    )
    app.state.public_route_prefixes = ("/health",)
    app.add_middleware(InboxMiddleware)
    if auth:
        app.add_middleware(
            AuthMiddleware, strategy=BearerTokenStrategy(token="host-token")
        )

    probe = APIRouter()

    @probe.get("/api/probe/context")
    async def context_probe(
        context: InboxExecutionContext = Depends(get_inbox_execution_context),
    ) -> dict[str, Any]:
        return {
            "inbox_id": context.inbox_id,
            "waba": context.platform_account_id,
            "mode": context.routing_mode.value,
            "ambient": get_current_inbox_context(),
        }

    @probe.get("/api/probe/local")
    async def local_probe() -> dict[str, Any]:
        return {"ambient": get_current_inbox_context()}

    app.include_router(probe)
    app.include_router(create_whatsapp_router(include_template_transport=True))
    return app, session


@pytest.fixture
def explicit() -> tuple[FastAPI, _RecordingSession, _Resolver]:
    resolver = _Resolver()
    app, session = _app(resolver, mode=InboxRoutingMode.EXPLICIT)
    return app, session, resolver


@pytest.fixture
def legacy() -> tuple[FastAPI, _RecordingSession, _Resolver]:
    resolver = _Resolver()
    app, session = _app(resolver, mode=InboxRoutingMode.LEGACY)
    return app, session, resolver


# ── selection semantics ────────────────────────────────────────────────────


def test_header_selects_the_context_and_binds_logging_scope(explicit: Any) -> None:
    app, _, resolver = explicit
    response = TestClient(app).get(
        "/api/probe/context", headers={INBOX_ID_HEADER: INBOX_B}
    )

    assert response.status_code == 200
    assert response.json() == {
        "inbox_id": INBOX_B,
        "waba": "waba-b",
        "mode": "explicit",
        "ambient": INBOX_B,
    }
    assert resolver.calls == [INBOX_B]


def test_explicit_mode_requires_the_header(explicit: Any) -> None:
    app, _, resolver = explicit
    response = TestClient(app).get("/api/probe/context")

    assert response.status_code == 400
    assert INBOX_ID_HEADER in response.json()["detail"]
    assert resolver.calls == []


@pytest.mark.parametrize("bad", ["a:b", "a b", "x*", "a__b", "x" * 129])
def test_malformed_header_is_400_before_any_directory_call(
    explicit: Any, bad: str
) -> None:
    app, _, resolver = explicit
    resolver.failure = InboxDirectoryUnavailableError("down")
    response = TestClient(app).get("/api/probe/context", headers={INBOX_ID_HEADER: bad})

    assert response.status_code == 400
    assert resolver.calls == []


def test_unknown_or_inactive_header_is_404(explicit: Any) -> None:
    app, _, _ = explicit
    response = TestClient(app).get(
        "/api/probe/context", headers={INBOX_ID_HEADER: "333333333333333"}
    )

    assert response.status_code == 404
    assert "333333333333333" in response.json()["detail"]


@pytest.mark.parametrize(
    "failure",
    [InboxDirectoryUnavailableError("down"), InboxCredentialIntegrityError("bad key")],
)
def test_directory_and_decrypt_failures_are_503_not_unknown(
    explicit: Any, failure: Exception
) -> None:
    app, _, resolver = explicit
    resolver.failure = failure
    response = TestClient(app).get(
        "/api/probe/context", headers={INBOX_ID_HEADER: INBOX_A}
    )

    assert response.status_code == 503


def test_legacy_mode_uses_its_default_and_accepts_the_same_header(legacy: Any) -> None:
    app, _, _ = legacy
    client = TestClient(app)

    assert client.get("/api/probe/context").json()["inbox_id"] == INBOX_A
    assert (
        client.get("/api/probe/context", headers={INBOX_ID_HEADER: INBOX_A}).json()[
            "inbox_id"
        ]
        == INBOX_A
    )


def test_legacy_mode_cannot_introduce_a_second_inbox_by_header(legacy: Any) -> None:
    app, _, resolver = legacy
    resolver.inboxes.pop(INBOX_B)
    response = TestClient(app).get(
        "/api/probe/context", headers={INBOX_ID_HEADER: INBOX_B}
    )

    assert response.status_code == 404


def test_context_does_not_leak_between_sequential_requests(explicit: Any) -> None:
    app, _, _ = explicit
    client = TestClient(app)

    scoped = client.get("/api/probe/context", headers={INBOX_ID_HEADER: INBOX_A})
    local = client.get("/api/probe/local")

    assert scoped.json()["ambient"] == INBOX_A
    assert local.json() == {"ambient": None}


def test_host_authorization_runs_before_inbox_resolution() -> None:
    resolver = _Resolver()
    app, _ = _app(resolver, mode=InboxRoutingMode.EXPLICIT, auth=True)
    client = TestClient(app)

    denied = client.get("/api/probe/context", headers={INBOX_ID_HEADER: INBOX_A})
    allowed = client.get(
        "/api/probe/context",
        headers={INBOX_ID_HEADER: INBOX_A, "Authorization": "Bearer host-token"},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 200
    # A valid Inbox header alone granted nothing: only the authorized call resolved.
    assert resolver.calls == [INBOX_A]


# ── the route capability matrix ────────────────────────────────────────────

INBOX_DEPENDENT: list[tuple[str, str, Any]] = [
    (
        "POST",
        "/api/whatsapp/messages/send-text",
        {"recipient": "573001234567", "text": "hi"},
    ),
    ("POST", "/api/whatsapp/messages/mark-as-read", {"message_id": "wamid.1"}),
    (
        "POST",
        "/api/whatsapp/media/send-image",
        {"recipient": "573001234567", "media_source": "https://x/y.jpg"},
    ),
    (
        "POST",
        "/api/whatsapp/interactive/send-cta",
        {
            "recipient": "573001234567",
            "body": "b",
            "button_text": "t",
            "button_url": "https://x",
        },
    ),
    (
        "POST",
        "/api/whatsapp/specialized/send-location-request",
        {"recipient": "573001234567", "body": "where?"},
    ),
    ("GET", "/api/whatsapp/media/info/12345", None),
    ("GET", "/api/whatsapp/media/download/12345", None),
    ("DELETE", "/api/whatsapp/media/12345", None),
    ("GET", "/api/whatsapp/templates/info", None),
    ("GET", "/api/whatsapp/templates/info/by-id/42", None),
    ("GET", "/api/whatsapp/templates/info/by-name/welcome", None),
    ("GET", "/api/whatsapp/templates/info/namespace", None),
    ("GET", "/api/whatsapp/health", None),
    (
        "POST",
        "/api/whatsapp/state-handlers/set",
        {
            "recipient": "573001234567",
            "handler_config": {"handler_value": "flow", "ttl_seconds": 600},
        },
    ),
    ("GET", "/api/whatsapp/state-handlers/get/573001234567/flow", None),
    ("DELETE", "/api/whatsapp/state-handlers/delete/573001234567/flow", None),
    (
        "POST",
        "/api/whatsapp/templates/send-text",
        {
            "kind": "text",
            "recipient": {"kind": "phone_number", "value": "573001234567"},
            "template_name": "welcome",
            "category": "utility",
        },
    ),
    (
        "POST",
        "/api/whatsapp/templates/send-media",
        {
            "kind": "media",
            "recipient": {"kind": "phone_number", "value": "573001234567"},
            "template_name": "welcome",
            "category": "utility",
            "media_header": {"media_type": "image", "media_id": "123"},
        },
    ),
]

# Media upload takes multipart rather than JSON, so it carries its own case.
MEDIA_UPLOAD = ("POST", "/api/whatsapp/media/upload")

LOCAL_ONLY: list[tuple[str, str, Any]] = [
    ("GET", "/api/whatsapp/messages/limits", None),
    ("GET", "/api/whatsapp/media/limits", None),
    ("GET", "/api/whatsapp/interactive/limits", None),
    ("GET", "/api/whatsapp/templates/limits", None),
    (
        "POST",
        "/api/whatsapp/specialized/validate-coordinates",
        {"latitude": 4.6, "longitude": -74.1},
    ),
    (
        "POST",
        "/api/whatsapp/specialized/validate-contact",
        {
            "name": {"formatted_name": "A", "first_name": "A"},
            "phones": [{"phone": "+573001234567"}],
        },
    ),
]


def _call(
    client: TestClient,
    method: str,
    path: str,
    body: Any,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return client.request(method, path, json=body, headers=headers or {})


@pytest.mark.parametrize(
    ("method", "path", "body"), INBOX_DEPENDENT, ids=[p for _, p, _ in INBOX_DEPENDENT]
)
def test_inbox_dependent_routes_follow_the_selection_matrix(
    explicit: Any, method: str, path: str, body: Any
) -> None:
    app, _, resolver = explicit
    client = TestClient(app)

    assert _call(client, method, path, body).status_code == 400, "no header"
    assert (
        _call(client, method, path, body, {INBOX_ID_HEADER: "a:b"}).status_code == 400
    ), "malformed"
    assert (
        _call(
            client, method, path, body, {INBOX_ID_HEADER: "333333333333333"}
        ).status_code
        == 404
    ), "unknown"
    resolver.failure = InboxDirectoryUnavailableError("down")
    assert (
        _call(client, method, path, body, {INBOX_ID_HEADER: INBOX_A}).status_code == 503
    ), "unavailable"
    resolver.failure = None
    resolver.calls.clear()
    response = _call(client, method, path, body, {INBOX_ID_HEADER: INBOX_A})
    assert response.status_code not in (400, 401, 403, 404, 503), (path, response.text)
    assert resolver.calls == [INBOX_A], "exactly one directory resolution per request"


@pytest.mark.parametrize(
    ("method", "path", "body"), INBOX_DEPENDENT, ids=[p for _, p, _ in INBOX_DEPENDENT]
)
def test_inbox_dependent_routes_use_the_legacy_default(
    legacy: Any, method: str, path: str, body: Any
) -> None:
    app, _, resolver = legacy
    response = _call(TestClient(app), method, path, body)

    assert response.status_code not in (400, 401, 403, 404, 503), (path, response.text)
    assert resolver.calls == [INBOX_A]


@pytest.mark.parametrize(
    ("method", "path", "body"), LOCAL_ONLY, ids=[p for _, p, _ in LOCAL_ONLY]
)
def test_local_only_routes_ignore_headers_and_directory_health(
    explicit: Any, method: str, path: str, body: Any
) -> None:
    app, _, resolver = explicit
    resolver.failure = InboxDirectoryUnavailableError("down")
    client = TestClient(app)

    for headers in (
        {},
        {INBOX_ID_HEADER: "a:b"},
        {INBOX_ID_HEADER: "333333333333333"},
        {INBOX_ID_HEADER: INBOX_A},
    ):
        response = _call(client, method, path, body, headers)
        assert response.status_code == 200, (path, headers, response.text)
    assert resolver.calls == []


def test_media_download_resolves_metadata_with_the_selected_inbox(
    explicit: Any,
) -> None:
    app, session, _ = explicit
    response = TestClient(app).get(
        "/api/whatsapp/media/info/777", headers={INBOX_ID_HEADER: INBOX_B}
    )

    assert response.status_code == 200
    (meta_call,) = [r for r in session.requests if "/777" in r["url"]]
    assert meta_call["headers"]["Authorization"] == f"Bearer token-{INBOX_B}"


def test_template_info_derives_the_waba_only_from_the_record(explicit: Any) -> None:
    app, session, _ = explicit
    response = TestClient(app).get(
        "/api/whatsapp/templates/info",
        params={"waba_id": "attacker"},
        headers={INBOX_ID_HEADER: INBOX_B},
    )

    assert response.status_code == 200
    (call,) = session.requests
    assert "/waba-b/" in call["url"]
    assert "attacker" not in call["url"]
    assert call["headers"]["Authorization"] == f"Bearer token-{INBOX_B}"


def test_openapi_documents_the_header_on_every_inbox_dependent_route() -> None:
    """The header must be visible in /openapi.json, not only in a constant.

    Callers read the schema, so declaring the header is what makes the
    "selection, not authorization" semantics reachable.
    """
    from wappa.api.dependencies.inbox_context import INBOX_HEADER_DESCRIPTION

    app = FastAPI()
    app.include_router(create_whatsapp_router(include_template_transport=True))
    spec = app.openapi()

    documented: dict[str, Any] = {}
    undocumented: set[str] = set()
    for path, operations in spec["paths"].items():
        for operation in operations.values():
            header = next(
                (
                    parameter
                    for parameter in operation.get("parameters", [])
                    if parameter["name"] == INBOX_ID_HEADER
                ),
                None,
            )
            if header is None:
                undocumented.add(path)
            else:
                documented[path] = header

    for path in (
        "/api/whatsapp/messages/send-text",
        "/api/whatsapp/media/upload",
        "/api/whatsapp/media/info/{media_id}",
        "/api/whatsapp/templates/info",
        "/api/whatsapp/templates/send-text",
        "/api/whatsapp/state-handlers/set",
        "/api/whatsapp/health",
    ):
        assert path in documented, f"{path} does not document {INBOX_ID_HEADER}"

    assert undocumented == {
        "/api/whatsapp/messages/limits",
        "/api/whatsapp/media/limits",
        "/api/whatsapp/interactive/limits",
        "/api/whatsapp/templates/limits",
        "/api/whatsapp/specialized/validate-contact",
        "/api/whatsapp/specialized/validate-coordinates",
    }

    header = documented["/api/whatsapp/messages/send-text"]
    assert header["in"] == "header"
    assert header["required"] is False, "legacy mode may omit it; explicit mode 400s"
    assert header["description"] == INBOX_HEADER_DESCRIPTION
    assert "grants no permission" in header["description"]
    assert "not a credential" in header["description"]


async def test_execution_context_repr_hides_the_token(explicit: Any) -> None:
    app, _, resolver = explicit
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [(b"x-wappa-inbox-id", INBOX_A.encode())],
        "query_string": b"",
        "app": app,
    }
    context = await get_inbox_execution_context(Request(scope))

    assert f"token-{INBOX_A}" not in repr(context)
    assert context.account_ref == PlatformAccountRef.whatsapp("waba-a")


def test_media_upload_follows_the_same_selection_matrix(explicit: Any) -> None:
    """The one mutation an embedded host keeps is Inbox-dependent too."""
    app, _, resolver = explicit
    client = TestClient(app)
    method, path = MEDIA_UPLOAD

    def upload(headers: dict[str, str] | None = None) -> httpx.Response:
        return client.request(
            method,
            path,
            files={"file": ("a.jpg", b"bytes", "image/jpeg")},
            headers=headers or {},
        )

    assert upload().status_code == 400
    assert upload({INBOX_ID_HEADER: "a:b"}).status_code == 400
    assert upload({INBOX_ID_HEADER: "333333333333333"}).status_code == 404
    resolver.failure = InboxDirectoryUnavailableError("down")
    assert upload({INBOX_ID_HEADER: INBOX_A}).status_code == 503
    resolver.failure = None
    resolver.calls.clear()
    assert upload({INBOX_ID_HEADER: INBOX_A}).status_code not in (400, 404, 503)
    assert resolver.calls == [INBOX_A]


async def test_context_does_not_leak_between_concurrent_requests(
    explicit: Any,
) -> None:
    """Concurrent requests must each observe their own Inbox, never a neighbour's.

    Sequential isolation is not proof: a ContextVar bound without a per-request
    token would still pass the sequential test and fail here.
    """
    import asyncio

    app, _, _ = explicit

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        wanted = [INBOX_A, INBOX_B] * 12
        responses = await asyncio.gather(
            *(
                client.get("/api/probe/context", headers={INBOX_ID_HEADER: inbox_id})
                for inbox_id in wanted
            )
        )

    observed = [response.json() for response in responses]
    assert [entry["inbox_id"] for entry in observed] == wanted
    assert [entry["ambient"] for entry in observed] == wanted
    assert {entry["waba"] for entry in observed} == {"waba-a", "waba-b"}


async def test_concurrent_local_only_requests_never_bind_an_inbox(
    explicit: Any,
) -> None:
    """A neighbour's Inbox must not bleed into a route that resolves none."""
    import asyncio

    app, _, resolver = explicit

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        results = await asyncio.gather(
            *(
                client.get("/api/probe/context", headers={INBOX_ID_HEADER: INBOX_A})
                if index % 2
                else client.get("/api/probe/local")
                for index in range(24)
            )
        )

    for index, response in enumerate(results):
        if index % 2:
            assert response.json()["ambient"] == INBOX_A
        else:
            assert response.json() == {"ambient": None}
    assert set(resolver.calls) == {INBOX_A}
