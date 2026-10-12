"""Explicit public distribution boundaries; never glob research workspaces."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.3.0"
EPOCH = 1791763200  # 2026-10-12 00:00:00 UTC
ZIP_TIME = (2026, 10, 12, 0, 0, 0)
PREFIX = "luna-repro-sdk/"
RUNTIME = tuple("luna_repro/" + name for name in ("__init__.py", "__main__.py", "client.py", "source.py", "adapters.py", "selection.py", "session.py", "connection.py", "capture.py"))
EXAMPLES = tuple("examples/" + name for name in (
    "README.md", "toy.py", "walkthrough.py", "pasa_adapter.py",
    "last_cell.ipynb", "incremental.ipynb", "walkthrough.ipynb", "quickstart.ipynb", "auto_select.py"))
LEGACY = tuple(sorted(("pyproject.toml", "README.md", "LICENSE", *RUNTIME, *EXAMPLES)))
DOCS = tuple("docs/" + name for name in ("installation-ko.md", "installation-en.md", "usage-ko.md", "usage-en.md", "selection-ko.md", "selection-en.md"))
GUIDES = tuple(sorted(("README.md", "README.en.md", "LICENSE", *DOCS, *EXAMPLES)))
TESTS = tuple("tests/" + name for name in (
    "test_sdk.py", "test_source.py", "test_walkthrough.py", "test_pasa_intake.py", "test_distribution.py", "test_selection.py", "test_adapters.py", "test_connection.py"))
SCRIPTS = tuple("scripts/" + name for name in (
    "release_spec.py", "audit_public.py", "build_release.py", "validate_release.py"))
PUBLIC = tuple(sorted(set((*LEGACY, *GUIDES, *TESTS, *SCRIPTS,
                         "CHANGELOG.md", "SECURITY.md", ".gitignore", ".gitattributes"))))
