"""Run with: python -m unittest discover -s tests -v (no Django/database)."""

import base64
import contextlib
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

SDK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SDK_ROOT
sys.path.insert(0, str(SDK_ROOT))

import luna_repro as repro
from luna_repro.client import MAX_BUNDLE_BYTES, _checked_bundle

PROJECT = "12345678-1234-5678-1234-567812345678"
TOKEN = "unit-test-project-token-which-is-never-real"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def module(name):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "examples" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Receiver(BaseHTTPRequestHandler):
    requests = []
    mode = "ok"

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append((self.path, self.headers.get("Authorization"), payload))
        if self.server.mode == "redirect":
            self.send_response(307)
            self.send_header("Location", "http://127.0.0.1:%d/stolen/" % self.server.server_port)
            self.end_headers()
            return
        if self.server.mode == "reject":
            self.send_response(403)
            self.end_headers()
            self.wfile.write(("Secret reflected: " + TOKEN).encode())
            return
        if self.server.mode in {"quota", "rate", "trashed"}:
            self.send_response(429 if self.server.mode == "rate" else 409)
            self.send_header("Retry-After", "900")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"quota": "storage_quota", "rate": "rate_limited", "trashed": "result_trashed"}[self.server.mode], "private_details": TOKEN}).encode())
            return
        receipt = {"page_id": payload["page_id"], "revision": 1, "url": "http://127.0.0.1:%d/repro/%s/" % (self.server.server_port, payload["page_id"]), "unsafe_remote_field": TOKEN}
        if self.server.mode == "wrong_id":
            receipt["page_id"] = str(uuid.uuid4())
        if self.server.mode == "wrong_origin":
            receipt["url"] = "https://other.example/report/"
        if self.server.mode == "secret_url":
            receipt["url"] += "?token=" + TOKEN
        data = json.dumps(receipt).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@contextlib.contextmanager
def receiver(mode="ok"):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    server.requests, server.mode = [], mode
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, "http://127.0.0.1:%d" % server.server_port
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class SDKTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def page(self, **kwargs):
        result = repro.page(PROJECT, "합성 결과", outbox=self.root / "outbox", **kwargs)
        result.section("quality", "품질").metrics({"RMSE": 0.25, "count": 3}).image(PNG)
        return result

    def test_contract_and_stable_request_identity(self):
        page = self.page()
        first = page.bundle()
        self.assertEqual(first["schema"], "luna.repro.page.v1")
        self.assertEqual(page.bundle(), first)
        self.assertNotIn(str(REPO_ROOT), json.dumps(first))
        page.section("notes").text("Second result")
        changed = page.bundle()
        self.assertNotEqual(changed["request_id"], first["request_id"])
        self.assertEqual(changed["page_id"], first["page_id"])
        self.assertEqual(changed["run_id"], first["run_id"])

    def test_explicit_computing_source_is_distinct_from_registration(self):
        page = self.page()
        default = page.bundle()["sections"][0]["source"]
        self.assertEqual(default["file"], "test_sdk.py")
        self.assertIn("line_start", default)
        reference = {"file": "notebook.ipynb", "cell_id": "inference", "url": "https://example.org/notebook#inference"}
        page.section("quality", source=reference)
        self.assertEqual(page.bundle()["sections"][0]["source"], reference)

    def test_page_computation_source_is_inherited_without_registration_fields(self):
        declared = {"url": "https://example.org/inference.py#L40", "file": "inference.py", "line_start": 40, "commit": "a" * 40}
        page = repro.page(PROJECT, "Declared computation", source=declared)
        page.section("result").metrics({"RMSE": 0.1})
        self.assertEqual(page.bundle()["sections"][0]["source"], declared)
        page.source["line_start"] = 90
        self.assertEqual(page.bundle()["sections"][0]["source"]["line_start"], 40)
        explicit = {"file": "registration.py", "line_start": 12}
        page.section("registered", source=explicit).text("Selected output")
        self.assertEqual(page.bundle()["sections"][1]["source"], explicit)

    def test_only_selected_values_and_files_are_saved(self):
        unselected_secret = "private-source-never-selected"
        (self.root / "other.py").write_text(unselected_secret)
        page = self.page(token=TOKEN, endpoint="https://example.org")
        saved = page.save(self.root / "result.json")
        text = saved.read_text(encoding="utf-8")
        self.assertNotIn(TOKEN, text)
        self.assertNotIn(unselected_secret, text)
        self.assertNotIn("endpoint", text)
        loaded = repro.load_bundle(saved)
        self.assertEqual(loaded, page.bundle())

    def test_credentials_selected_accidentally_are_refused_before_save(self):
        page = self.page(token=TOKEN)
        page.section("oops").text(TOKEN)
        with self.assertRaisesRegex(ValueError, "credential"):
            page.save(self.root / "bad.json")
        self.assertFalse((self.root / "bad.json").exists())
        page._token = None
        with self.assertRaisesRegex(ValueError, "credential"):
            page.publish(token=TOKEN)
        self.assertFalse((self.root / "outbox").exists())

    def test_source_urls_reject_credentials_query_and_insecure_links(self):
        for url in ("https://user:password@example.org/code", "https://example.org/code?token=secret", "http://example.org/code", "javascript:alert(1)", "https://localhost/code", "https://192.168.1.1/code", "https://example.org/code%3Ftoken=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.page(source={"url": url})

    def test_source_hashes_and_repository_paths_are_validated_before_upload(self):
        for source in ({"commit": "main"}, {"snapshot_sha256": "not-a-hash"}, {"file": "../private.py"}, {"file": "C:\\private.py"}, {"line_start": 4, "line_end": 2}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.page(source=source)

    def test_endpoint_rejects_remote_http_and_auth_in_url(self):
        bundle = self.page().bundle()
        for endpoint in ("http://example.org", "https://u:p@example.org", "https://example.org?token=secret", "file:///tmp"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                repro.publish_bundle(bundle, endpoint=endpoint, token=TOKEN)

    def test_finite_metrics_and_table_shape(self):
        page = self.page()
        for value in (math.inf, -math.inf, math.nan, True, "0.2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                page.section("invalid").metrics({"x": value})
        with self.assertRaises(ValueError):
            page.section("invalid").table(["x"], [[1, 2]])
        with self.assertRaises(ValueError):
            page.section("invalid").table(["x"], [[math.nan]])

    def test_dataframe_duck_typing_requires_only_selected_frame(self):
        class Frame:
            columns = ["name", "value"]
            def __len__(self):
                return 2
            def itertuples(self, *, index, name):
                self.args = (index, name)
                return iter([("a", 1), ("b", 2)])
        frame = Frame()
        page = self.page()
        page.section("table").table(frame)
        self.assertEqual(frame.args, (False, None))
        self.assertEqual(page.bundle()["sections"][-1]["blocks"][0]["rows"], [["a", 1], ["b", 2]])

    def test_matplotlib_duck_figure_exports_one_png(self):
        class Figure:
            def savefig(self, output, *, format, bbox_inches):
                self.args = (format, bbox_inches)
                output.write(PNG)
        figure = Figure()
        page = self.page()
        page.section("plot").figure(figure, "selected figure")
        self.assertEqual(figure.args, ("png", "tight"))
        self.assertEqual(len(page.bundle()["artifacts"]), 1)

    def test_image_directory_svg_and_corruption_are_refused(self):
        page = self.page()
        with self.assertRaises(ValueError):
            page.section("bad").image(self.root)
        with self.assertRaises(ValueError):
            page.section("bad").image(b"<svg/>")
        bundle = self.page().bundle()
        bundle["artifacts"][0]["sha256"] = "0" * 64
        (self.root / "tampered.json").write_text(json.dumps(bundle))
        with self.assertRaisesRegex(ValueError, "checksum"):
            repro.load_bundle(self.root / "tampered.json")

    def test_unknown_fields_and_unreferenced_artifacts_are_refused(self):
        bundle = self.page().bundle()
        bundle["token"] = TOKEN
        with self.assertRaises(ValueError):
            _checked_bundle(bundle)
        del bundle["token"]
        bundle["sections"][0]["blocks"].pop()
        with self.assertRaises(ValueError):
            _checked_bundle(bundle)

    def test_whole_bundle_size_limit_is_enforced_before_saving(self):
        with patch("luna_repro.client.MAX_BUNDLE_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "16 MiB"):
                self.page().save(self.root / "too-large.json")
        self.assertFalse((self.root / "too-large.json").exists())

    def test_no_endpoint_preserves_pending_without_claiming_success(self):
        page = self.page(token=TOKEN)
        outcome = page.publish()
        self.assertEqual(outcome["status"], "pending")
        self.assertTrue(Path(outcome["outbox_path"]).exists())
        self.assertNotIn(TOKEN, json.dumps(outcome))

    def test_real_loopback_publish_retry_receipt_and_secret_redaction(self):
        page = self.page(token=TOKEN)
        with receiver() as (server, endpoint):
            outcome = page.publish(endpoint=endpoint)
            self.assertEqual(outcome["status"], "published")
            self.assertEqual(server.requests[0][0], "/api/repro/v1/pages/")
            self.assertEqual(server.requests[0][1], "Bearer " + TOKEN)
            self.assertNotIn(TOKEN, json.dumps(outcome))
            receipt_files = list((self.root / "outbox").glob("*.receipt.json"))
            self.assertEqual(len(receipt_files), 1)
            self.assertNotIn(TOKEN, receipt_files[0].read_text())
            self.assertEqual(repro.sync(self.root / "outbox", endpoint=endpoint, token=TOKEN), [])
            self.assertEqual(len(server.requests), 1)

    def test_redirect_never_forwards_bearer(self):
        page = self.page(token=TOKEN)
        with receiver("redirect") as (server, endpoint):
            result = page.publish(endpoint=endpoint)
            self.assertEqual(result["status"], "pending")
            self.assertEqual(len(server.requests), 1)
            self.assertEqual(server.requests[0][0], "/api/repro/v1/pages/")

    def test_remote_error_body_does_not_escape_and_strict_is_explicit(self):
        page = self.page(token=TOKEN)
        with receiver("reject") as (_, endpoint):
            with self.assertRaises(repro.PublishError) as caught:
                page.publish(endpoint=endpoint, strict=True)
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertIn("403", str(caught.exception))
        self.assertTrue(list((self.root / "outbox").glob("*.json")))

    def test_storage_quota_and_rate_limits_are_distinct_without_raw_error_leak(self):
        for mode, code in (("quota", "storage_quota"), ("rate", "rate_limited")):
            with self.subTest(mode=mode), receiver(mode) as (server, endpoint):
                result = self.page(token=TOKEN).publish(endpoint=endpoint)
                self.assertEqual(result["status"], "pending")
                self.assertEqual(result["code"], code)
                self.assertEqual(result["retry_after"], 900)
                self.assertNotIn(TOKEN, json.dumps(result))
                self.assertEqual(len(server.requests), 1)

    def test_trashed_result_remains_pending_and_never_auto_restores(self):
        with receiver("trashed") as (server, endpoint):
            result = self.page(token=TOKEN).publish(endpoint=endpoint)
            self.assertEqual(result["status"], "pending")
            self.assertEqual(result["code"], "result_trashed")
            self.assertIn("Restore it in the platform", result["message"])
            self.assertTrue(Path(result["outbox_path"]).is_file())
            self.assertEqual(len(server.requests), 1)
            self.assertNotIn(TOKEN, json.dumps(result))

    def test_untrusted_receipt_identity_origin_or_secret_url_is_refused(self):
        for mode in ("wrong_id", "wrong_origin", "secret_url"):
            with self.subTest(mode=mode), receiver(mode) as (_, endpoint):
                result = self.page(token=TOKEN).publish(endpoint=endpoint)
                self.assertEqual(result["status"], "pending")

    def test_explicit_sync_reuses_pending_request_id(self):
        page = self.page(token=TOKEN)
        pending = page.publish()
        with receiver() as (server, endpoint):
            result = repro.sync(self.root / "outbox", endpoint=endpoint, token=TOKEN)
            self.assertEqual(result[0]["status"], "published")
            self.assertEqual(server.requests[0][2]["request_id"], pending["request_id"])

    def test_cli_refuses_bad_bundle_without_echoing_secret(self):
        path = self.root / "bad.json"
        path.write_text('{"token": "%s"}' % TOKEN)
        from luna_repro.__main__ import main
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["publish", str(path)])
        self.assertEqual(code, 1)
        self.assertNotIn(TOKEN, output.getvalue())


class ExampleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def pasa_fixture(self):
        parameters = {"run_name": "synthetic-fixture", "names": ["lower", "upper"], "methods": ["surfels"], "iterations": 3}
        (self.root / "run_manifest.json").write_text(json.dumps({"status": "complete", "parameters": parameters}))
        (self.root / "camera_checks.json").write_text(json.dumps([{"sequence": "lower", "points": 12, "camera_consistency_pass": True}, {"sequence": "upper", "points": 10, "camera_consistency_pass": False}]))
        image = self.root / "surfels/lower/renders/003_render.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(PNG)

    def test_pasa_import_reports_camera_failure_and_missing_gt(self):
        self.pasa_fixture()
        adapter = module("pasa_adapter")
        page = adapter.build_page(self.root, project=PROJECT)
        bundle = page.bundle()
        self.assertEqual(bundle["evidence"], {"origin": "imported", "execution_status": "completed", "evaluation_status": "not_run"})
        cameras = next(s for s in bundle["sections"] if s["key"] == "cameras")
        self.assertIn("Fail", cameras["blocks"][0]["rows"][1][2])
        self.assertEqual(len(bundle["artifacts"]), 1)
        self.assertEqual(adapter.build_page(self.root, project=PROJECT).page_id, page.page_id)

    def test_pasa_evaluation_requires_recorded_rows_and_gt_assertion(self):
        self.pasa_fixture()
        evaluation = self.root / "evaluation"
        evaluation.mkdir()
        (evaluation / "comparison.csv").write_text("method,chamfer\nsurfels,0.01\n")
        adapter = module("pasa_adapter")
        self.assertEqual(adapter.build_page(self.root, project=PROJECT).evidence["evaluation_status"], "not_run")
        self.assertEqual(adapter.build_page(self.root, project=PROJECT, gt_available=True).evidence["evaluation_status"], "completed")

    def test_pasa_manifest_path_escape_is_refused(self):
        self.pasa_fixture()
        path = self.root / "run_manifest.json"
        manifest = json.loads(path.read_text())
        manifest["parameters"]["methods"] = ["../private"]
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "safe path"):
            module("pasa_adapter").build_page(self.root, project=PROJECT)

    def test_toy_is_deterministic_and_actually_computes_two_methods(self):
        toy = module("toy")
        first, second = toy.build_pages(PROJECT), toy.build_pages(PROJECT)
        self.assertEqual(len(first), 2)
        for left, right in zip(first, second):
            left_bundle, right_bundle = left.bundle(), right.bundle()
            self.assertEqual(left_bundle["evidence"]["origin"], "synthetic")
            self.assertEqual(left_bundle["sections"], right_bundle["sections"])
            self.assertEqual(left_bundle["artifacts"], right_bundle["artifacts"])
        baseline = first[0].bundle()["sections"][0]["blocks"][0]["values"]["RMSE"]
        smooth = first[1].bundle()["sections"][0]["blocks"][0]["values"]["RMSE"]
        self.assertGreater(baseline, smooth)
        self.assertGreater(smooth, 0)

    def test_notebook_examples_have_no_outputs_and_valid_python_cells(self):
        paths = list((REPO_ROOT / "examples").glob("*.ipynb"))
        self.assertEqual({path.name for path in paths},
                         {"last_cell.ipynb", "incremental.ipynb", "walkthrough.ipynb"})
        for path in paths:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    self.assertEqual(cell["outputs"], [])
                    self.assertIsNone(cell["execution_count"])
                    compile("".join(cell["source"]), str(path), "exec")

    def test_notebook_examples_execute_offline_with_actual_sdk(self):
        old_directory = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, {}, clear=True):
                for path in (REPO_ROOT / "examples").glob("*.ipynb"):
                    namespace = {"__name__": "__main__"}
                    notebook = json.loads(path.read_text(encoding="utf-8"))
                    for cell in notebook["cells"]:
                        if cell["cell_type"] == "code":
                            with contextlib.redirect_stdout(io.StringIO()):
                                exec(compile("".join(cell["source"]), str(path), "exec"), namespace)
            bundles = list((self.root / ".luna-repro").glob("*.json"))
            self.assertEqual(len(bundles), 3)
            for path in bundles:
                self.assertEqual(repro.load_bundle(path)["evidence"]["origin"], "synthetic")
        finally:
            os.chdir(old_directory)


if __name__ == "__main__":
    unittest.main()
