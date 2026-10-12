"""Distribution boundaries and bilingual runnable documentation."""
import contextlib
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_public import audit
from build_release import zip_bytes
from release_spec import EPOCH, LEGACY, PREFIX, ZIP_TIME


class DistributionTests(unittest.TestCase):
    def test_public_allowlist_and_synthetic_content(self):
        self.assertEqual(audit()["status"], "passed")

    def test_legacy_archive_is_exact_and_repeatable(self):
        first = zip_bytes(ROOT, LEGACY, PREFIX)
        self.assertEqual(first, zip_bytes(ROOT, LEGACY, PREFIX))
        self.assertEqual(len(LEGACY), 21)
        self.assertEqual(datetime.fromtimestamp(EPOCH, timezone.utc).strftime("%Y-%m-%d"), "2026-10-12")
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertEqual(archive.namelist(), [PREFIX + name for name in sorted(LEGACY)])
            for entry in archive.infolist():
                self.assertEqual(entry.date_time, ZIP_TIME)
                self.assertEqual(entry.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(entry.create_system, 3)
                self.assertEqual(entry.external_attr, 0o100644 << 16)
                self.assertEqual(archive.read(entry), (ROOT / entry.filename.removeprefix(PREFIX)).read_bytes())

    def test_bilingual_readme_examples_are_offline_by_default(self):
        @contextlib.contextmanager
        def working_directory(path):
            original = Path.cwd()
            try:
                os.chdir(path)
                yield
            finally:
                os.chdir(original)
        with tempfile.TemporaryDirectory() as folder, working_directory(folder), patch.dict(os.environ, {}, clear=True), \
                    patch("socket.create_connection", side_effect=AssertionError("No network")), \
                    patch("getpass.getpass", side_effect=AssertionError("No credential prompt")):
            for name in ("README.md", "README.en.md"):
                source = (ROOT / name).read_text(encoding="utf-8")
                namespace = {"__name__": "__main__"}
                for code in re.findall(r"```python\n(.*?)\n```", source, flags=re.S):
                    with contextlib.redirect_stdout(io.StringIO()):
                        exec(compile(code, name, "exec"), namespace)
                self.assertEqual(namespace["mae"], 0.5)
                self.assertFalse(namespace["PUBLISH"])
            self.assertEqual(len(list(Path(".luna-repro").glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
