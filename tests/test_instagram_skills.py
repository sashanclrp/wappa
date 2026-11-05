"""Shipped developer skills: imports they teach exist, examples run, emission is safe."""

import importlib
import re
from pathlib import Path

import pytest

from wappa.cli.main import SKILLS_SOURCE, _emit_skills

SKILLS = ("wappa-instagram-apps", "wappa-conversational-scores", "wappa-runtime-state")
IMPORT = re.compile(r"^\s*from (wappa[\w.]*) import ([\w, ()]+)$", re.MULTILINE)


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
        SKILLS_SOURCE / "wappa-runtime-state/references/isolation-tests.md"
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
    edited = tmp_path / ".claude/skills/wappa-runtime-state/SKILL.md"
    edited.write_text("user edit")
    again = _emit_skills(tmp_path)
    assert edited.read_text() == "user edit"
    assert all("kept existing" in n for n in again)
