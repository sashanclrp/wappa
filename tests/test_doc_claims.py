"""Keep the agent-read docs honest.

Agents and humans copy what these docs say. Each check below turns one kind of
doc claim into something CI verifies:

(a) every backticked repo path exists;
(b) every ``wappa`` import in a fenced python block resolves;
(c) every fenced python block compiles;
(d) retired names stay retired: ``recipient=`` on Messenger ``send_*`` calls,
    and ``LOG_LEVEL`` / ``API_VERSION`` / ``ENVIRONMENT`` as documented env
    vars (Settings reads ``SYSTEM_LOG_LEVEL``, ``META_API_VERSION`` and
    ``SYSTEM_ENVIRONMENT``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from doc_contract import path_contract_errors, python_contract_errors, split_markdown

from wappa.cli.scaffold import SKILLS_SOURCE

pytestmark = pytest.mark.documentation

REPO = Path(__file__).resolve().parents[1]

# ── Doc set ──────────────────────────────────────────────────────────────────


def _markdown_docs() -> list[Path]:
    docs = [
        REPO / name
        for name in ("README.md", "AGENTS.md", "CODING_STANDARDS.md", "CONTEXT.md")
    ]
    docs.append(REPO / "ARCHITECTURE.md")
    docs.extend(sorted((REPO / "wappa").rglob("ARCHITECTURE.md")))
    docs.append(REPO / "docs" / "public-contract.md")
    docs.extend(sorted(REPO.glob(".agents/skills/wappa-*/**/*.md")))
    return [
        doc
        for doc in docs
        if doc.is_file() and not doc.resolve().is_relative_to(SKILLS_SOURCE.resolve())
    ]


def _env_examples() -> list[Path]:
    return sorted(REPO.glob("wappa/cli/examples/*/.env.example"))


MARKDOWN_DOCS = _markdown_docs()
ENV_EXAMPLES = _env_examples()


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


# ── (a) backticked paths exist ───────────────────────────────────────────────


def test_doc_set_is_not_empty() -> None:
    required = {
        REPO / name
        for name in (
            "README.md",
            "AGENTS.md",
            "CODING_STANDARDS.md",
            "CONTEXT.md",
            "ARCHITECTURE.md",
            "docs/public-contract.md",
        )
    }
    assert required <= set(MARKDOWN_DOCS)
    assert ENV_EXAMPLES
    assert any(split_markdown(doc)[0] for doc in MARKDOWN_DOCS)


def test_backticked_paths_exist() -> None:
    errors = [error for doc in MARKDOWN_DOCS for error in path_contract_errors(doc)]
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("doc", MARKDOWN_DOCS, ids=_rel)
def test_documented_python_matches_the_runtime(doc: Path) -> None:
    errors = python_contract_errors(doc)
    assert not errors, "\n".join(errors)


RETIRED_ENV_VARS = ("LOG_LEVEL", "API_VERSION", "ENVIRONMENT")
_RETIRED_ENV_LINE = re.compile(
    r"^\s*#?\s*(?:export\s+)?(?P<key>" + "|".join(RETIRED_ENV_VARS) + r")\s*="
)


@pytest.mark.parametrize("env_example", ENV_EXAMPLES, ids=_rel)
def test_env_examples_do_not_document_retired_env_vars(env_example: Path) -> None:
    hits = [
        f"{_rel(env_example)}:{lineno}: {match['key']}"
        for lineno, line in enumerate(env_example.read_text().splitlines(), start=1)
        if (match := _RETIRED_ENV_LINE.match(line))
    ]
    assert not hits, "Retired env vars (use SYSTEM_*/META_*):\n" + "\n".join(hits)


def test_retired_env_vars_are_not_read_by_settings() -> None:
    source = (REPO / "wappa" / "core" / "config" / "settings.py").read_text()
    for name in RETIRED_ENV_VARS:
        assert f'"{name}"' not in source, f"Settings reads {name}; update this test"


def test_async_sqlalchemy_is_a_declared_dependency() -> None:
    """Regression: SQLAlchemy 2.1 made greenlet optional, breaking a clean install."""
    import tomllib

    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    assert any(
        dep.startswith("sqlalchemy[asyncio]")
        for dep in pyproject["project"]["dependencies"]
    )


def test_build_settings_use_the_key_hatchling_reads() -> None:
    """Regression: [tool.hatchling.build] is silently ignored."""
    import tomllib

    tool = tomllib.loads(Path("pyproject.toml").read_text())["tool"]
    assert "hatchling" not in tool
    sdist = tool["hatch"]["build"]["targets"]["sdist"]
    assert {"/.agents/", "/.claude/"} <= set(sdist["exclude"])
    assert sdist["skip-excluded-dirs"] is True


def test_repository_and_shipped_skill_docs_have_separate_owners() -> None:
    repository_docs = [doc.resolve() for doc in MARKDOWN_DOCS]
    shipped_docs = {doc.resolve() for doc in SKILLS_SOURCE.rglob("*.md")}
    assert len(repository_docs) == len(set(repository_docs)), (
        "A document is checked through multiple paths"
    )
    assert set(repository_docs).isdisjoint(shipped_docs)
