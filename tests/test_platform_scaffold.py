"""Every installed Platform's adapters keep the one scaffold, and no module grows into a god file.

The scaffold is written down in
``.agents/skills/wappa-develop/references/scaffolding.md``; this test is its
executable half. A Platform whose outbound or inbound adapter leaves the shape,
an outbound "handler", ``utils`` or ``services`` folder, a Platform prefix on a
file inside its own folder, a translator that imports back into the pure
models, or any Wappa module over the size ceiling fails here. Changing the
scaffold means changing that reference, this test and the context
``ARCHITECTURE.md`` trees in one change.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from wappa.platforms import PLATFORMS

WAPPA = Path(__file__).resolve().parents[1] / "wappa"
INSTALLED = sorted(platform.value for platform in PLATFORMS)

# Entries every outbound adapter has: a file, or a package (``name/``).
OUTBOUND_REQUIRED = (
    "__init__.py",
    "platform_messenger.py",
    "client.py",
    "errors.py",
    "messenger/__init__.py",
    "messenger/adapter.py",
    "payloads/",
    "media/rules.py",
    "media/library.py",
)
INBOUND_REQUIRED = (
    "__init__.py",
    "fields.py",
    "routing.py",
    "models/",
    "message_types/context.py",
    "processor/__init__.py",
    "processor/adapter.py",
)
BANNED_DIRS = frozenset({"handlers", "utils", "helpers", "services"})

# Lines per module. A module past this with several responsibilities is split
# into a package named after its stem (``refactor-backend-god-files`` skill).
CEILING = 450


def _exists(root: Path, entry: str) -> bool:
    if entry.endswith("/"):
        return (root / entry.rstrip("/")).is_dir()
    if (root / entry).is_file():
        return True
    # ``transport.py`` may be a ``transport/`` package.
    return (root / entry.removesuffix(".py") / "__init__.py").is_file()


@pytest.mark.parametrize("platform", INSTALLED)
@pytest.mark.parametrize(
    ("side", "required"),
    [("messaging", OUTBOUND_REQUIRED), ("webhooks", INBOUND_REQUIRED)],
)
def test_each_platform_adapter_has_the_scaffold(
    platform: str, side: str, required: tuple[str, ...]
) -> None:
    root = WAPPA / side / platform
    missing = [entry for entry in required if not _exists(root, entry)]
    assert missing == [], f"wappa/{side}/{platform}/ is missing {missing}"


@pytest.mark.parametrize("platform", INSTALLED)
@pytest.mark.parametrize("side", ["messaging", "webhooks"])
def test_adapter_folders_use_scaffold_names(platform: str, side: str) -> None:
    root = WAPPA / side / platform
    problems: list[str] = []
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(WAPPA).as_posix()
        if path.is_dir() and path.name in BANNED_DIRS:
            problems.append(f"{rel}/: name the module after what it does")
        if path.suffix == ".py" and path.name.startswith(f"{platform}_"):
            problems.append(f"{rel}: drop the Platform prefix inside its own folder")
        if path.is_dir():
            modules = [p for p in path.glob("*.py") if p.name != "__init__.py"]
            subpackages = [
                p for p in path.iterdir() if p.is_dir() and p.name != "__pycache__"
            ]
            if len(modules) == 1 and not subpackages:
                problems.append(f"{rel}/: one module in a folder is a shallow package")
    assert problems == []


def test_no_platform_processor_outside_its_adapter() -> None:
    assert not (WAPPA / "processors").exists(), (
        "Platform translators live in wappa/webhooks/<platform>/processor/"
    )


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(("." * node.level) + node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("platform", INSTALLED)
def test_pure_inbound_models_never_import_the_translator(platform: str) -> None:
    root = WAPPA / "webhooks" / platform
    offenders = []
    for folder in ("models", "message_types"):
        for path in sorted((root / folder).rglob("*.py")):
            if any("processor" in name.split(".") for name in _imports(path)):
                offenders.append(path.relative_to(WAPPA).as_posix())
    assert offenders == []


def test_no_module_is_a_god_file() -> None:
    oversized = {}
    for path in sorted(WAPPA.rglob("*.py")):
        rel = path.relative_to(WAPPA).as_posix()
        if rel.startswith("cli/examples/"):
            continue
        lines = len(path.read_text().splitlines())
        if lines > CEILING:
            oversized[rel] = lines
    assert oversized == {}, (
        f"Modules over {CEILING} lines; split them into a package "
        f"(refactor-backend-god-files): {oversized}"
    )
