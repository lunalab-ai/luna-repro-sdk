"""Execute teaching assets with the actual SDK, synthetic inputs and no secrets."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import luna_repro as repro
from test_sdk import receiver


def walkthrough():
    spec = importlib.util.spec_from_file_location("walkthrough_under_test", ROOT / "examples/walkthrough.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class WalkthroughTests(unittest.TestCase):
    def test_source_handbook_file_example_runs_with_actual_selected_definition(self):
        with tempfile.TemporaryDirectory() as temporary, working_directory(temporary), \
                patch("socket.create_connection", side_effect=AssertionError("No network")), \
                patch.dict(os.environ, {}, clear=True):
            for language in ("ko", "en"):
                text = (ROOT / f"docs/usage-{language}.md").read_text(encoding="utf-8")
                chapter = text.split("\n## 12.", 1)[1]
                code = re.findall(r"```python\n(.*?)\n```", chapter, flags=re.S)[0]
                path = Path(temporary) / ("source_example_" + language + ".py")
                path.write_text(code, encoding="utf-8")
                spec = importlib.util.spec_from_file_location("source_handbook_" + language, path)
                module = importlib.util.module_from_spec(spec)
                with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(module)
                bundle = repro.load_bundle(module.saved)
                self.assertEqual(bundle["sections"][0]["blocks"][0]["values"]["MAE"], 0.5)
                self.assertIn("def calculate():", bundle["sections"][0]["source"]["provenance"]["snapshot"]["text"])

    def test_notebook_opt_in_selects_actual_saved_cell_without_outputs(self):
        notebook_path = ROOT / "examples/walkthrough.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary, working_directory(temporary), \
                patch("socket.create_connection", side_effect=AssertionError("No network")), \
                patch.dict(os.environ, {}, clear=True):
            namespace = {"__name__": "__main__"}
            for cell in notebook["cells"]:
                if cell["cell_type"] != "code": continue
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile("".join(cell["source"]), str(notebook_path), "exec"), namespace)
                if cell["id"] == "setup":
                    namespace.update(INCLUDE_SOURCE=True, SOURCE_NOTEBOOK=notebook_path)
            for page in namespace["pages"]:
                source = page.bundle()["source"]
                self.assertEqual(source["cell_id"], "calculation-and-pages")
                self.assertEqual(source["provenance"]["role"], "reference")
                self.assertIn("def calculate():", source["provenance"]["snapshot"]["text"])
                self.assertNotIn('"outputs"', source["provenance"]["snapshot"]["text"])

    def test_opt_in_source_definitions_preserve_exact_local_code(self):
        with patch("socket.create_connection", side_effect=AssertionError("No network")):
            pages = walkthrough().build_pages(include_source=True)
        for page in pages:
            bundle = page.bundle()
            self.assertTrue(all(section["source"]["provenance"]["snapshot"]["text"] for section in bundle["sections"]))
            self.assertIn('def summarize(', bundle["sections"][1]["source"]["provenance"]["snapshot"]["text"])
            self.assertIn('def chart_png(', bundle["sections"][2]["source"]["provenance"]["snapshot"]["text"])

    def test_computation_and_bundles_are_deterministic_without_network_or_disk(self):
        with patch("socket.create_connection", side_effect=AssertionError("No network")), \
                patch("pathlib.Path.open", side_effect=AssertionError("No files")):
            first = walkthrough().build_pages()
            second = walkthrough().build_pages()
            for index, (left, right) in enumerate(zip(first, second)):
                a, b = left.bundle(), right.bundle()
                self.assertEqual(a["sections"], b["sections"])
                self.assertEqual(a["artifacts"], b["artifacts"])
                self.assertEqual(a["evidence"], {"origin": "synthetic", "execution_status": "completed", "evaluation_status": "completed"})
                values = a["sections"][1]["blocks"][0]["values"]
                self.assertAlmostEqual(values["MAE"], 0.5 if index == 0 else 0.1)
                self.assertAlmostEqual(values["RMSE"], 0.5 if index == 0 else 0.1)
                self.assertEqual(values["samples"], 6)

    def test_cli_default_saves_locally_and_preserves_separate_runs(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True), \
                patch("getpass.getpass", side_effect=AssertionError("No prompt")), \
                patch("socket.create_connection", side_effect=AssertionError("No network")):
            module = walkthrough()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(["--output", temporary]), 0)
                self.assertEqual(module.main(["--output", temporary]), 0)
            saved = list(Path(temporary).glob("*/*.json"))
            self.assertEqual(len(saved), 4)
            self.assertEqual(len({path.parent for path in saved}), 2)
            self.assertFalse(list(Path(temporary).glob("*/outbox")))
            for path in saved:
                self.assertEqual(repro.load_bundle(path)["evidence"]["origin"], "synthetic")

    def test_cli_rejects_example_project_before_prompt_or_transmission(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("getpass.getpass", side_effect=AssertionError("No prompt")), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            walkthrough().main(["--publish"])
        self.assertEqual(exc.exception.code, 2)

    def test_explicit_cli_publication_uses_real_sdk_and_loopback_receipts(self):
        with tempfile.TemporaryDirectory() as temporary, receiver() as (server, endpoint), \
                patch.dict(os.environ, {"LUNA_REPRO_ENDPOINT": endpoint,
                                       "LUNA_REPRO_TOKEN": "synthetic-walkthrough-test-key"}, clear=True):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = walkthrough().main(["--project", "12345678-1234-5678-1234-567812345679",
                                            "--output", temporary, "--publish"])
            self.assertEqual(code, 0)
            self.assertEqual(len(server.requests), 2)
            self.assertEqual(len(list(Path(temporary).glob("*/outbox/*.receipt.json"))), 2)
            self.assertEqual(output.getvalue().count("Published:"), 2)
            self.assertNotIn("synthetic-walkthrough-test-key", output.getvalue())

    def test_failed_explicit_cli_publication_is_pending_and_preserved(self):
        with tempfile.TemporaryDirectory() as temporary, receiver("quota") as (server, endpoint), \
                patch.dict(os.environ, {"LUNA_REPRO_ENDPOINT": endpoint,
                                       "LUNA_REPRO_TOKEN": "synthetic-walkthrough-test-key"}, clear=True):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = walkthrough().main(["--project", "12345678-1234-5678-1234-567812345679",
                                            "--output", temporary, "--publish"])
            self.assertEqual(code, 1)
            self.assertEqual(len(server.requests), 2)
            self.assertEqual(len(list(Path(temporary).glob("*/outbox/*.json"))), 2)
            self.assertNotIn("Published:", output.getvalue())
            self.assertIn("storage_quota", output.getvalue())

    def test_notebook_run_all_is_offline_and_uses_notebook_provenance(self):
        path = ROOT / "examples/walkthrough.ipynb"
        notebook = json.loads(path.read_text(encoding="utf-8"))
        directory = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as temporary, working_directory(temporary), \
                    patch.dict(os.environ, {}, clear=True), \
                    patch("getpass.getpass", side_effect=AssertionError("No prompt")), \
                    patch("socket.create_connection", side_effect=AssertionError("No network")):
                namespace = {"__name__": "__main__"}
                for cell in notebook["cells"]:
                    self.assertFalse(cell.get("attachments"))
                    if cell["cell_type"] == "code":
                        self.assertEqual(cell["outputs"], [])
                        self.assertIsNone(cell["execution_count"])
                        with contextlib.redirect_stdout(io.StringIO()):
                            exec(compile("".join(cell["source"]), str(path), "exec"), namespace)
                saved = list(Path(temporary).glob(".luna-repro/walkthrough-notebook/*/*.json"))
                self.assertEqual(len(saved), 2)
                for path in saved:
                    bundle = repro.load_bundle(path)
                    self.assertEqual(bundle["source"], {"file": "walkthrough.ipynb", "cell_id": "calculation-and-pages"})
                    self.assertTrue(all(section["source"] == bundle["source"] for section in bundle["sections"]))
                self.assertFalse(namespace["PUBLISH"])
                self.assertFalse(namespace["RETRY"])
        finally:
            os.chdir(directory)

    def test_bilingual_complete_examples_execute_without_implicit_publication(self):
        directory = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as temporary, working_directory(temporary), \
                    patch.dict(os.environ, {}, clear=True), \
                    patch("socket.create_connection", side_effect=AssertionError("No network")):
                for language in ("ko", "en"):
                    text = (ROOT / f"docs/usage-{language}.md").read_text(encoding="utf-8")
                    sections = re.split(r"(?m)^## ", text)
                    self.assertGreaterEqual(len(sections), 13)
                    for section_number in (1, 3):
                        code = re.findall(r"```python\n(.*?)\n```", sections[section_number], flags=re.S)[0]
                        namespace = {"__name__": "__main__"}
                        with contextlib.redirect_stdout(io.StringIO()):
                            exec(compile(code, f"guide-{language}-section-{section_number}", "exec"), namespace)
                        bundle = namespace["page"].bundle()
                        self.assertEqual(bundle["evidence"]["origin"], "synthetic")
                        self.assertEqual(bundle["evidence"]["evaluation_status"], "completed")
                    for code in re.findall(r"```python\n(.*?)\n```", text, flags=re.S):
                        if code.lstrip().startswith("%pip"):
                            continue  # Explicit notebook installation magic.
                        compile(code, f"guide-{language}-syntax", "exec")
        finally:
            os.chdir(directory)


if __name__ == "__main__":
    unittest.main()
