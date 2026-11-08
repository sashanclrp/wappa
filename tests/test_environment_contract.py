"""Clustered deployment settings fail fast on retired names."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from wappa.core.config.settings import Settings

RETIRED = {
    "WP_WEBHOOK_VERIFY_TOKEN": "META_WEBHOOK_VERIFY_TOKEN",
    "WP_ACCESS_TOKEN": "META_WHATSAPP_ACCESS_TOKEN",
    "WP_PHONE_ID": "META_WHATSAPP_PHONE_NUMBER_ID",
    "WP_BID": "META_WHATSAPP_BUSINESS_ACCOUNT_ID",
    "OPENAI_API_KEY": "LLM_PROVIDER_OPENAI_API_KEY",
    "WAPPA_STRICT_META_SCHEMA": "SYSTEM_STRICT_META_SCHEMA",
}
ROOT = Path(__file__).resolve().parents[1]


def run_process(
    tmp_path: Path, variables: dict[str, str], code: str
) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in RETIRED and not key.startswith(("META_", "SYSTEM_", "REDIS_"))
    }
    env.update(variables, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


@pytest.mark.parametrize("old,replacement", RETIRED.items())
@pytest.mark.parametrize("value", ["", "secret-must-not-be-printed"])
def test_retired_names_refuse_process_start_even_when_empty(
    tmp_path: Path, old: str, replacement: str, value: str
) -> None:
    result = run_process(tmp_path, {old: value}, "import wappa")
    assert result.returncode != 0
    assert f"{old} was renamed to {replacement}" in result.stderr
    assert "0.34.3" in result.stderr
    assert "secret-must-not-be-printed" not in result.stderr


def test_replacement_does_not_override_a_retired_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for old in RETIRED:
        monkeypatch.delenv(old, raising=False)
    for old, replacement in RETIRED.items():
        with monkeypatch.context() as environment:
            environment.setenv(old, "")
            environment.setenv(replacement, "replacement-value")
            with pytest.raises(ValueError) as error:
                Settings()
            assert f"{old} was renamed to {replacement}" in str(error.value)
            assert "replacement-value" not in str(error.value)


@pytest.mark.parametrize("mode", ["legacy", "explicit"])
def test_new_environment_starts_and_answers_meta_challenge(
    tmp_path: Path, mode: str
) -> None:
    variables = {
        "META_APP_SECRET": "dummy-app-secret",
        "META_WEBHOOK_VERIFY_TOKEN": "clustered-verify",
        "SYSTEM_INBOX_ROUTING_MODE": mode,
    }
    if mode == "legacy":
        variables.update(
            META_WHATSAPP_ACCESS_TOKEN="dummy-token",
            META_WHATSAPP_PHONE_NUMBER_ID="111",
            META_WHATSAPP_BUSINESS_ACCOUNT_ID="222",
        )
    result = run_process(
        tmp_path,
        variables,
        """
from fastapi.testclient import TestClient
from wappa import Wappa, WappaEventHandler
from wappa.core.config import settings
from wappa.core.security import CredentialCodec

class Handler(WappaEventHandler):
    async def process_message(self, webhook):
        pass

class Source:
    async def get_inbox(self, inbox_ref):
        return None
    async def list_inboxes_for_platform_account(self, account_ref):
        return ()

kwargs = {}
if settings.inbox_routing_mode == "explicit":
    settings.system_token_enc_key = CredentialCodec.generate_key()
    kwargs["inbox_directory_source"] = Source()
app = Wappa(cache="memory", **kwargs)
app.set_event_handler(Handler())
with TestClient(app.asgi) as client:
    response = client.get("/webhook/inboxes/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "clustered-verify", "hub.challenge": "challenge-343"})
    assert response.status_code == 200, response.text
    assert response.text == "challenge-343", response.text
    response = client.get("/health/detailed")
    assert response.status_code == 200, response.text
    assert "openai" not in response.json()["platform_configs"]
""",
    )
    assert result.returncode == 0, result.stderr + result.stdout


@pytest.mark.parametrize(
    "name",
    [
        "META_WHATSAPP_ACCESS_TOKEN",
        "META_WHATSAPP_PHONE_NUMBER_ID",
        "META_WHATSAPP_BUSINESS_ACCOUNT_ID",
    ],
)
def test_explicit_environment_rejects_each_deployment_credential(
    tmp_path: Path, name: str
) -> None:
    result = run_process(
        tmp_path,
        {name: "dummy-value", "SYSTEM_INBOX_ROUTING_MODE": "explicit"},
        """
from wappa import Wappa, WappaEventHandler
class Handler(WappaEventHandler):
    async def process_message(self, webhook): pass
class Source:
    async def get_inbox(self, inbox_ref): return None
    async def list_inboxes_for_platform_account(self, account_ref): return ()
app = Wappa(cache="memory", inbox_directory_source=Source())
app.set_event_handler(Handler())
app.asgi
""",
    )
    assert result.returncode != 0
    assert "Explicit Inbox routing rejects" in result.stderr
    assert name in result.stderr
    assert "dummy-value" not in result.stderr


def test_package_environment_reads_use_owned_clusters() -> None:
    """Host examples may read their own clustered provider configuration."""
    for path in (ROOT / "wappa").rglob("*.py"):
        tree = ast.parse(path.read_text())
        constants = {
            node.targets[0].id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
        }
        prefixes = ("SYSTEM_", "META_", "REDIS_")
        if path.is_relative_to(ROOT / "wappa/cli/examples"):
            prefixes += ("LLM_PROVIDER_",)
        for node in ast.walk(tree):
            key = None
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and ast.unparse(node.func) in {"os.getenv", "os.environ.get"}
            ):
                key = node.args[0]
            elif (
                isinstance(node, ast.Subscript)
                and ast.unparse(node.value) == "os.environ"
            ):
                key = node.slice
            if key is None:
                continue
            if isinstance(key, ast.Constant):
                name = key.value
            elif isinstance(key, ast.Name):
                name = constants.get(key.id)
            else:
                name = None
            assert isinstance(name, str), (
                f"Unresolved environment read: {path}:{node.lineno}"
            )
            assert name.startswith(prefixes) or name in {
                "PORT",
                "DATABASE_URL",
                "REDIS_URL",
            }, f"{path}:{node.lineno}: {name}"
