"""Shipped Host skills: what they teach exists, their structure holds, emission is safe."""

import importlib
import re
from pathlib import Path

import pytest

from wappa.cli.main import SKILLS_SOURCE, _emit_skills

SKILLS = (
    "wappa-apps",
    "wappa-conversational-scores",
    "wappa-state-and-storage",
    "wappa-host-integration",
)
IMPORT = re.compile(r"^\s*from (wappa[\w.]*) import ([\w, ()]+)$", re.MULTILINE)


MESSENGER_CALL = re.compile(r"self\.(messenger|whatsapp|instagram)\.(\w+)\(")
SIBLING = re.compile(r"`(wappa-[a-z-]+)`")
REFERENCE = re.compile(r"`references/([\w-]+\.md)`")


def _markdown_files() -> list[Path]:
    return [p for s in SKILLS for p in (SKILLS_SOURCE / s).rglob("*.md")]


def test_collection_is_complete():
    for name in SKILLS:
        root = SKILLS_SOURCE / name
        assert (root / "SKILL.md").is_file()
        assert (root / "agents" / "openai.yaml").is_file()
        assert (root / "evals" / "evals.json").is_file()


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: p.name)
def test_every_taught_wappa_import_exists(path: Path):
    text = path.read_text()
    for module, names in IMPORT.findall(text):
        mod = importlib.import_module(module)
        for name in names.replace("(", "").replace(")", "").split(","):
            name = name.strip()
            if name:
                assert hasattr(mod, name), f"{path.name}: {module}.{name} missing"


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: p.name)
def test_no_legacy_recipient_keyword_is_taught(path: Path):
    blocks = path.read_text().split("```")[1::2]
    assert all("recipient=" not in block for block in blocks)


async def test_isolation_reference_example_runs():
    source = (
        SKILLS_SOURCE / "wappa-state-and-storage/references/isolation-tests.md"
    ).read_text()
    code = source.split("```python", 1)[1].split("```", 1)[0]
    namespace: dict = {}
    exec(compile(code, "isolation-tests.md", "exec"), namespace)  # noqa: S102
    await namespace["test_same_native_id_never_shares_state"]()
    await namespace["test_miss_is_none_and_delete_clears"]()


def test_emit_skills_creates_both_lanes_and_never_overwrites(tmp_path: Path):
    notes = _emit_skills(tmp_path)
    for name in SKILLS:
        claude = tmp_path / ".claude/skills" / name
        agents = tmp_path / ".agents/skills" / name
        assert (claude / "SKILL.md").read_text() == (agents / "SKILL.md").read_text()
    assert sum("created" in n for n in notes) == len(SKILLS)
    edited = tmp_path / ".claude/skills/wappa-state-and-storage/SKILL.md"
    edited.write_text("user edit")
    again = _emit_skills(tmp_path)
    assert edited.read_text() == "user edit"
    assert all("kept existing" in n for n in again)


def test_skill_folders_match_the_shipped_set():
    shipped = {p.name for p in SKILLS_SOURCE.iterdir() if (p / "SKILL.md").is_file()}
    assert shipped == set(SKILLS)


@pytest.mark.parametrize("name", SKILLS)
def test_frontmatter_and_references_are_consistent(name: str):
    root = SKILLS_SOURCE / name
    text = (root / "SKILL.md").read_text()
    front = text.split("---", 2)[1]
    assert f"name: {name}" in front
    description = front.split("description:", 1)[1].strip().splitlines()[0]
    assert len(description) <= 1024
    assert len(text.splitlines()) <= 500
    linked = set(REFERENCE.findall(text))
    on_disk = {p.name for p in (root / "references").glob("*.md")}
    assert linked <= on_disk, f"{name}: SKILL.md links missing {linked - on_disk}"
    assert on_disk <= linked, f"{name}: orphaned references {on_disk - linked}"


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: p.name)
def test_every_named_sibling_skill_ships(path: Path):
    for sibling in SIBLING.findall(path.read_text()):
        assert sibling in SKILLS, f"{path.name}: names unknown skill {sibling}"


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: p.name)
def test_every_taught_messenger_method_exists(path: Path):
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.messaging.instagram import InstagramMessenger
    from wappa.messaging.whatsapp import WhatsAppMessenger

    owners = {
        "messenger": (IMessenger,),
        "whatsapp": (WhatsAppMessenger,),
        "instagram": (InstagramMessenger,),
    }
    for owner, method in MESSENGER_CALL.findall(path.read_text()):
        assert any(hasattr(cls, method) for cls in owners[owner]), (
            f"{path.name}: self.{owner}.{method}() does not exist"
        )
