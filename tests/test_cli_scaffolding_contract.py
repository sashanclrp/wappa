"""A scaffolded project must speak v0.27 contracts (PRD 5).

`wappa init` is a teaching surface: whatever it writes is what the next
application believes about credentials, routing, and the callback. These tests
scaffold a real project and read back what a developer would get.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wappa.cli.main import app as cli_app

RENAMED_OR_REMOVED = (
    "IInboxCredentialStore",
    "inbox_credential_store",
    "DatabaseInboxCredentialStore",
    "SettingsInboxCredentialStore",
    "wappa_inboxes",
    'inbox_routing="auto"',
    "webhook/inboxes/{inbox_id}",
    "webhook/messenger/",
    "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_ID",
)


@pytest.fixture
def scaffolded(tmp_path: Path) -> Path:
    result = CliRunner().invoke(cli_app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path


def test_init_scaffolds_the_documented_structure(scaffolded: Path) -> None:
    for relative in (
        "app/__init__.py",
        "app/main.py",
        "app/master_event.py",
        "app/scores/__init__.py",
        ".gitignore",
        ".env",
    ):
        assert (scaffolded / relative).is_file(), relative


def test_scaffolded_env_teaches_the_meta_application_configuration(
    scaffolded: Path,
) -> None:
    env = (scaffolded / ".env").read_text()

    assert "META_APP_SECRET=" in env
    assert "WP_WEBHOOK_VERIFY_TOKEN=" in env
    # The legacy bundle is what this template runs on, and it must be complete.
    for variable in ("WP_ACCESS_TOKEN=", "WP_PHONE_ID=", "WP_BID="):
        assert variable in env, variable


def test_scaffolded_env_names_the_one_callback_and_both_modes(
    scaffolded: Path,
) -> None:
    env = (scaffolded / ".env").read_text()

    assert "/webhook/inboxes/whatsapp" in env
    assert "legacy" in env and "explicit" in env
    assert "docs/migration/v0.27.0-multi-inbox.md" in env


def test_scaffolded_project_carries_no_removed_contract(scaffolded: Path) -> None:
    for path in scaffolded.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text()
        for stale in RENAMED_OR_REMOVED:
            assert stale not in text, f"{path.name} still teaches {stale!r}"


def test_scaffolded_app_uses_the_current_public_import_surface(
    scaffolded: Path,
) -> None:
    """The generated code must import only names v0.27 actually exports."""
    import wappa

    for relative in ("app/main.py", "app/master_event.py"):
        source = (scaffolded / relative).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "wappa":
                for alias in node.names:
                    assert hasattr(wappa, alias.name), (
                        f"{relative} imports wappa.{alias.name}, which does not exist"
                    )


def test_scaffolded_handler_matches_the_current_event_handler_contract(
    scaffolded: Path,
) -> None:
    from wappa import WappaEventHandler

    source = (scaffolded / "app/master_event.py").read_text()

    assert "WappaEventHandler" in source
    # process_message is the one abstract hook a generated handler must define.
    assert "async def process_message" in source
    assert "process_message" in WappaEventHandler.__abstractmethods__


def test_init_banner_teaches_the_callback_secret_and_url(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli_app, ["init", str(tmp_path)])

    assert "META_APP_SECRET" in result.output
    assert "/webhook/inboxes/whatsapp" in result.output
    assert "WP_WEBHOOK_VERIFY_TOKEN" in result.output
