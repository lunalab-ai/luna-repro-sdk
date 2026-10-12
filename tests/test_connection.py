"""Synthetic browser-pairing protocol, no real remote connection."""
import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import unittest
from unittest.mock import patch

import luna_repro as repro
from luna_repro import connection, session

PROJECT = "12345678-1234-5678-1234-567812345678"
SECRET = "synthetic-claim-proof"


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        repro.clear()
        self.addCleanup(repro.clear)

    def responses(self):
        challenge = hashlib.sha256(SECRET.encode()).hexdigest()
        return [(200, {"ticket": "signed-test-ticket", "verification_url": "https://example.test/workspace/repro/connect/approve/?ticket=signed-test-ticket",
                       "user_code": challenge[:8].upper(), "interval": 1, "expires_in": 600}),
                (202, {"status": "pending"}),
                (200, {"project_id": PROJECT, "project_title": "Synthetic", "token": "synthetic-session-credential",
                       "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()})]

    def test_browser_pairing_memory_only_and_reuse(self):
        output = io.StringIO()
        with patch.object(connection.secrets, "token_urlsafe", return_value=SECRET), \
             patch.object(connection, "_post", side_effect=self.responses()) as post, \
             patch.object(connection.time, "sleep"), patch.object(connection.webbrowser, "open") as browser, \
             contextlib.redirect_stdout(output):
            result = repro.connect(PROJECT, endpoint="https://example.test", label="Jupyter")
            reused = repro.connect(PROJECT, endpoint="https://example.test")
        self.assertFalse(result["reused"])
        self.assertTrue(reused["reused"])
        self.assertEqual(post.call_count, 3)
        self.assertEqual(post.call_args_list[0].args[2]["label"], "Jupyter")
        self.assertEqual(post.call_args_list[1].args[2], {"ticket": "signed-test-ticket", "secret": SECRET})
        self.assertEqual(browser.call_count, 1)
        self.assertNotIn(SECRET, output.getvalue())
        self.assertNotIn("synthetic-session-credential", output.getvalue() + repr(result) + repr(session.current()))

    def test_wrong_approval_origin_rejected_before_browser_or_claim(self):
        responses = self.responses()
        responses[0][1]["verification_url"] = "https://other.test/workspace/repro/connect/approve/"
        with patch.object(connection.secrets, "token_urlsafe", return_value=SECRET), \
             patch.object(connection, "_post", side_effect=responses) as post, \
             patch.object(connection.webbrowser, "open") as browser:
            with self.assertRaises(repro.PublishError):
                repro.connect(PROJECT, endpoint="https://example.test")
        self.assertEqual(post.call_count, 1)
        browser.assert_not_called()
        self.assertIsNone(session.current())

    def test_timeout_is_bounded_and_no_background_polling(self):
        with patch.object(connection.secrets, "token_urlsafe", return_value=SECRET), \
             patch.object(connection, "_post", side_effect=self.responses()), \
             patch.object(connection.time, "monotonic", side_effect=[0, 2]), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(repro.PublishError) as caught:
                repro.connect(PROJECT, endpoint="https://example.test", timeout=1, open_browser=False)
        self.assertEqual(caught.exception.code, "connection_timeout")
        self.assertIsNone(session.current())

    def test_request_has_no_cookie_origin_bearer_or_redirect_handler(self):
        class Response:
            status = 202
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, limit):
                return b'{"status":"pending"}'
        with patch.object(connection.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = Response()
            connection._post("https://example.test", "/api/repro/v1/connect/claim/", {"ticket": "x", "secret": SECRET}, 3)
        request = build.return_value.open.call_args.args[0]
        self.assertNotIn("Cookie", request.headers)
        self.assertNotIn("Origin", request.headers)
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(json.loads(request.data)["secret"], SECRET)

    def test_reject_invalid_expiry_without_retaining_key(self):
        responses = self.responses()
        responses[-1][1]["expires_at"] = "bad"
        with patch.object(connection.secrets, "token_urlsafe", return_value=SECRET), \
             patch.object(connection, "_post", side_effect=[responses[0], responses[-1]]), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(repro.PublishError):
                repro.connect(PROJECT, endpoint="https://example.test", open_browser=False)
        self.assertIsNone(session.current())


if __name__ == "__main__":
    unittest.main()
