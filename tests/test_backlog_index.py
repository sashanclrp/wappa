"""Every active backlog item is listed in the backlog execution plan.

``docs/backlog/README.md`` makes ``BACKLOG-EXECUTION-PLAN.md`` the master index
of the ``drafts/``, ``pending/`` and ``in_progress/`` folders. A top-level
entry is either a standalone ``.md`` file or a feature series directory
(``YYMMDD-{feature}/`` with a ``plan.md``); nested PRDs belong to their
series' own plan, not to this index.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKLOG = Path(__file__).resolve().parents[1] / "docs" / "backlog"
PLAN = BACKLOG / "BACKLOG-EXECUTION-PLAN.md"
FOLDERS = ("drafts", "pending", "in_progress")

_LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")


def _active_entries() -> list[str]:
    entries = []
    for folder in FOLDERS:
        root = BACKLOG / folder
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                entries.append(f"{folder}/{child.name}/")
            elif child.suffix == ".md":
                entries.append(f"{folder}/{child.name}")
    return entries


def _plan_targets() -> set[str]:
    text = PLAN.read_text(encoding="utf-8")
    return {
        target.split("#", 1)[0].removeprefix("./")
        for target in _LINK_TARGET.findall(text)
    }


def _listed(entry: str, targets: set[str]) -> bool:
    if entry.endswith("/"):
        return any(target.startswith(entry) for target in targets)
    return entry in targets


def test_backlog_plan_exists() -> None:
    assert PLAN.is_file()


def test_every_active_backlog_entry_is_linked_from_the_plan() -> None:
    targets = _plan_targets()
    missing = [entry for entry in _active_entries() if not _listed(entry, targets)]
    assert not missing, f"Not linked from {PLAN.name} (regenerate it):\n" + "\n".join(
        missing
    )


def test_plan_links_point_at_existing_backlog_entries() -> None:
    stale = [
        target
        for target in sorted(_plan_targets())
        if target.startswith(FOLDERS) and not (BACKLOG / target).exists()
    ]
    assert not stale, f"{PLAN.name} links to removed items:\n" + "\n".join(stale)
