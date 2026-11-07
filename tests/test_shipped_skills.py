"""Shipped Host skills: what they teach exists, their structure holds, emission is safe."""

import re
from pathlib import Path

import pytest
from doc_contract import path_contract_errors, python_contract_errors

from wappa.cli.scaffold import SKILLS_SOURCE, _emit_skills

SKILLS = (
    "wappa-apps",
    "wappa-conversational-scores",
    "wappa-state-and-storage",
    "wappa-host-integration",
    "wappa-scheduled-tasks",
)
MESSENGER_CALL = re.compile(r"self\.(messenger|whatsapp|instagram)\.(\w+)\(")
SIBLING = re.compile(r"`(wappa-[a-z-]+)`")
REFERENCE = re.compile(r"`references/([\w-]+\.md)`")


def _markdown_files() -> list[Path]:
    return [p for s in SKILLS for p in (SKILLS_SOURCE / s).rglob("*.md")]


@pytest.mark.documentation
def test_collection_is_complete():
    for name in SKILLS:
        root = SKILLS_SOURCE / name
        assert (root / "SKILL.md").is_file()
        assert (root / "agents" / "openai.yaml").is_file()
        assert (root / "evals" / "evals.json").is_file()


def test_scheduled_testing_reference_example_runs():
    source = (SKILLS_SOURCE / "wappa-scheduled-tasks/references/testing.md").read_text()
    code = source.split("```python", 1)[1].split("```", 1)[0]
    exec(compile(code, "testing.md", "exec"), {})  # noqa: S102


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


@pytest.mark.documentation
def test_skill_folders_match_the_shipped_set():
    shipped = {p.name for p in SKILLS_SOURCE.iterdir() if (p / "SKILL.md").is_file()}
    assert shipped == set(SKILLS)


@pytest.mark.documentation
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


@pytest.mark.documentation
@pytest.mark.parametrize(
    "path", _markdown_files(), ids=lambda p: p.relative_to(SKILLS_SOURCE).as_posix()
)
def test_skill_document_matches_the_runtime(path: Path):
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.messaging.instagram import InstagramMessenger
    from wappa.messaging.whatsapp import WhatsAppMessenger

    errors = list(python_contract_errors(path))
    text = path.read_text()
    for sibling in SIBLING.findall(text):
        if sibling not in SKILLS:
            errors.append(f"{path}: names unknown skill {sibling}")
    owners = {
        "messenger": IMessenger,
        "whatsapp": WhatsAppMessenger,
        "instagram": InstagramMessenger,
    }
    for owner, method in MESSENGER_CALL.findall(text):
        if not hasattr(owners[owner], method):
            errors.append(f"{path}: self.{owner}.{method}() does not exist")
    errors.extend(path_contract_errors(path))
    assert not errors, "\n".join(errors)
