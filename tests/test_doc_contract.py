"""The documentation guard must reject broken examples, not just pass today's docs."""

from pathlib import Path

import pytest
from doc_contract import path_contract_errors, python_contract_errors

pytestmark = pytest.mark.documentation


@pytest.mark.parametrize(
    ("source", "problem"),
    [
        ("from wappa import (", "syntax error"),
        ("import wappa.missing_contract_module", "cannot import module"),
        ("from wappa import MissingContractName", "has no MissingContractName"),
        ('self.messenger.send_text("hi", recipient="u")', "send_text(recipient=...)"),
        (
            'self.whatsapp.templates.send_text_template("hi", recipient="u")',
            "send_text_template(recipient=...)",
        ),
    ],
    ids=["syntax", "module", "import-name", "core-send", "template-send"],
)
def test_broken_python_examples_have_source_diagnostics(
    tmp_path: Path, source: str, problem: str
):
    doc = tmp_path / "guide.md"
    doc.write_text(f"# Guide\n\n```python\n{source}\n```\n")
    errors = python_contract_errors(doc)
    assert len(errors) == 1
    assert f"{doc}:4:" in errors[0]
    assert problem in errors[0]


def test_multiline_imports_aliases_and_top_level_await_are_valid(tmp_path: Path):
    doc = tmp_path / "guide.md"
    doc.write_text("""```python
from wappa import (
    InboxRef as Ref,
    ScheduledEvent,
)
import wappa.scheduling as scheduling
# recipient= in a comment or string is not a removed API call.
example = "recipient=..."
await self.messenger.send_text("hi", target=target)
```
```json
{"not": "Python syntax"}
```
""")
    assert python_contract_errors(doc) == ()


def test_path_checks_resolve_beside_the_document_and_report_missing_paths(
    tmp_path: Path,
):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "sample.py").write_text("")
    doc = tmp_path / "guide.md"
    doc.write_text("Use `assets/sample.py` then `assets/missing.py`.\n")
    errors = path_contract_errors(doc)
    assert len(errors) == 1
    assert f"{doc}:1:" in errors[0]
    assert "assets/missing.py" in errors[0]


def test_indented_long_fences_keep_real_source_lines(tmp_path: Path):
    doc = tmp_path / "guide.md"
    doc.write_text(
        "- Example:\n\n  ````python3\n  import wappa.missing_contract_module\n  ````\n"
    )
    errors = python_contract_errors(doc)
    assert len(errors) == 1
    assert f"{doc}:4:" in errors[0]
