"""Synthetic result selection: no real project, credential, API or research data."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import luna_repro as repro
from luna_repro import session
from luna_repro.selection import _apply_rule

PROJECT = "12345678-1234-5678-1234-567812345678"
OTHER = "12345678-1234-5678-1234-567812345679"


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(repro.clear)
        repro.configure(PROJECT, endpoint="https://example.test", token="synthetic-session-credential", outbox=self.temp.name)

    def test_local_namespace_does_not_execute_unknown_objects_or_copy_secrets(self):
        class Hostile:
            @property
            def columns(self):
                raise AssertionError("property inspected")
            def __repr__(self):
                raise AssertionError("repr inspected")
            def __iter__(self):
                raise AssertionError("iterator inspected")
        namespace = {"metrics": {"mae": 0.5}, "access_token": 1, "secret": {"mae": 1},
                     "opaque": Hostile(), "text": "private free text", "credential_rows": [[1]], "_private": 2}
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            selection = repro.select(namespace=namespace, show=False)
            self.assertEqual(list(selection.candidates), ["metrics"])
            self.assertEqual(selection.bundle()["sections"][0]["blocks"][0]["values"], {"mae": 0.5})
            self.assertNotIn("synthetic-session", repr(session.current()))

    def test_unknown_metaclass_getattribute_not_executed(self):
        class HostileMeta(type):
            def __getattribute__(cls, name):
                raise AssertionError("metaclass inspected")
        class Hostile(metaclass=HostileMeta):
            pass
        self.assertEqual(repro.select(namespace={"unknown": Hostile()}, show=False).summary(), [])

    def test_default_scope_is_local_and_no_upload(self):
        def calculate():
            result_metrics = {"error": 0.5}
            return repro.select(show=False)
        with patch("luna_repro.selection.publish_bundle", side_effect=AssertionError("upload")):
            selection = calculate()
        self.assertEqual(selection.selected, ["result_metrics"])
        source = selection.bundle()["sections"][0]["source"]
        self.assertEqual(source["file"], "test_selection.py")
        self.assertEqual(source["provenance"]["role"], "registration")

    def test_common_settings_are_unchecked_but_failed_results_remain_recommended(self):
        selected = repro.select(namespace={"i": 1, "epoch": 3, "batch_size": 8, "learning_rate": 0.01,
                                          "loss": float("nan"), "accuracy": 0.0, "failed": True, "epoch_loss": 0.4}, show=False)
        self.assertEqual(set(selected.selected), {"loss", "accuracy", "failed", "epoch_loss"})
        self.assertEqual(len(selected.candidates), 8)
        self.assertIn("unchecked", selected.candidates["learning_rate"].reason)

    def test_preview_freezes_mutable_objects_and_same_request_is_sent(self):
        metrics = {"mae": 0.5}
        selection = repro.select(namespace={"metrics": metrics}, show=False)
        preview = selection.preview()
        original = selection.bundle()
        metrics["mae"] = 999
        self.assertEqual(selection.preview(), preview)
        with patch("luna_repro.selection.publish_bundle", return_value={"status": "published", "url": "https://example.test/result/"}) as send:
            selection.publish()
            selection.publish()
        self.assertEqual(send.call_args_list[0].args[0], original)
        self.assertEqual(send.call_args_list[1].args[0], original)
        self.assertEqual(len(list(Path(self.temp.name).glob("*.json"))), 2)
        selection.option("metrics", title="Revised")
        self.assertEqual(selection.bundle()["sections"][0]["blocks"][0]["values"]["mae"], 999)

    def test_rule_has_no_values_and_both_auto_opt_ins_required(self):
        selection = repro.select(namespace={"metrics": {"mae": 0.5}}, show=False)
        rule = Path(self.temp.name) / "rule.json"
        selection.save_rule(rule)
        self.assertNotIn("mae", rule.read_text())
        with patch("luna_repro.selection.Selection.publish", side_effect=AssertionError("upload")):
            repro.select(namespace={"metrics": {"mae": 0.7}}, rule=rule, show=False)
            with self.assertRaises(ValueError):
                repro.select(namespace={"metrics": {"mae": 0.7}}, rule=rule, auto=True, show=False)
        selection.save_rule(rule, auto_publish=True)
        with patch("luna_repro.selection.Selection.publish", return_value={"status": "pending"}) as send:
            repro.select(namespace={"metrics": {"mae": 0.7}}, rule=rule, auto=True, show=False)
            self.assertEqual(send.call_count, 1)
        with self.assertRaises(ValueError):
            repro.select(namespace={"metrics": [0.7]}, rule=rule, show=False)
        repro.configure(OTHER)
        with self.assertRaises(ValueError):
            repro.select(namespace={"metrics": {"mae": 0.7}}, rule=rule, show=False)

    def test_project_and_known_credential_guards(self):
        with self.assertRaises(ValueError):
            repro.select("synthetic-session-credential", show=False).bundle()
        selection = repro.select(1, show=False)
        selection.preview()
        repro.configure(OTHER)
        with self.assertRaises(ValueError):
            selection.publish()
        repro.clear()
        local = repro.select(namespace={"metric": 1}, show=False)
        self.assertEqual(len(local.summary()), 1)
        with self.assertRaises(ValueError):
            local.preview()

    def test_text_and_preview_are_escaped(self):
        selection = repro.select("<script>alert(1)</script>", show=False, title="<img src=x>")
        page = selection.preview()
        self.assertNotIn("<script>", page)
        self.assertNotIn("<img src=x>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("default-src 'none'", page)

    def test_order_titles_purpose_dont_remove_failed_results(self):
        selection = repro.select(namespace={"failed_metrics": {"accuracy": 0.0}, "runtime": 2, "baseline": 3},
                                purpose="accuracy runtime", show=False)
        self.assertEqual(set(selection.selected), {"failed_metrics", "runtime", "baseline"})
        self.assertIn("purpose_matches", selection.summary()[0])
        selection.edit(order=["baseline", "runtime", "failed_metrics"], title="Comparison")
        selection.option("runtime", title="Elapsed", description="seconds")
        bundle = selection.bundle()
        self.assertEqual([s["title"] for s in bundle["sections"]], ["baseline", "Elapsed", "failed_metrics"])

    def test_page_facade_preserves_identity_and_evidence(self):
        page = repro.page(PROJECT, "Synthetic", evidence={"origin": "synthetic"})
        page.section("metrics").metrics({"error": 1})
        before = page.bundle()
        with patch.object(page, "publish", return_value={"status": "pending"}) as send:
            repro.publish(page)
        self.assertEqual(send.call_args.kwargs["token"], "synthetic-session-credential")
        self.assertEqual(page.bundle(), before)

    def test_bounds_and_explicit_publish(self):
        with self.assertRaises(ValueError):
            repro.select(namespace={str(i): i for i in range(1001)}, show=False)
        with self.assertRaises(ValueError):
            repro.select(object(), show=False)
        with self.assertRaises(ValueError):
            repro.publish()
        with patch("luna_repro.selection.Selection.publish", return_value={"status": "pending"}) as send:
            repro.publish({"mae": 1}, title="Explicit")
            send.assert_called_once()

    def test_console_fallback_does_not_print_values(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            repro.select(namespace={"metric": 938492}, show=True)
        self.assertNotIn("938492", stream.getvalue())

    def test_widget_requires_review_and_invalidates_send_after_edit(self):
        try:
            import IPython
            import ipywidgets
        except ImportError:
            self.skipTest("Optional notebook widgets are not installed")
        selection = repro.select(namespace={"metrics": {"mae": 0.5}}, show=False)
        with patch.object(IPython, "get_ipython", return_value=object()), \
                patch("IPython.display.display") as display, \
                patch.object(selection, "publish", return_value={"status": "published"}) as send:
            selection.show()
            container = selection._widget
            review, publish = container.children[-2].children
            self.assertTrue(publish.disabled)
            publish.click()
            send.assert_not_called()
            review.click()
            self.assertFalse(publish.disabled)
            self.assertIn("iframe sandbox", display.call_args.args[0].data)
            container.children[1].value = "Edited title"
            self.assertTrue(publish.disabled)
            review.click()
            publish.click()
            self.assertEqual(send.call_count, 1)
            self.assertTrue(publish.disabled)

    def test_new_bilingual_guide_fences_run_offline(self):
        import re
        root = Path(__file__).resolve().parents[1]
        original = Path.cwd()
        try:
            os.chdir(self.temp.name)
            with patch("socket.create_connection", side_effect=AssertionError("network")), contextlib.redirect_stdout(io.StringIO()):
                for language in ("ko", "en"):
                    namespace = {"__name__": "__main__"}
                    for code in re.findall(r"```python\n(.*?)\n```", (root / f"docs/selection-{language}.md").read_text(encoding="utf-8"), re.S):
                        exec(compile(code, f"selection-guide-{language}", "exec"), namespace)
                    self.assertFalse(namespace["PUBLISH"])
                    self.assertFalse(namespace["ENABLE_AUTOMATIC_SEND"])
                    self.assertTrue(Path("preview.html").is_file())
        finally:
            os.chdir(original)


if __name__ == "__main__":
    unittest.main()
