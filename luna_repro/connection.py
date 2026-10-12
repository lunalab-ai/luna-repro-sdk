"""Explicit browser pairing. No local listener, credential file or background polling."""
from dataclasses import replace
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from uuid import UUID
import webbrowser

from .client import _NoRedirect, _url, PublishError
from . import session


def _post(endpoint, path, payload, timeout):
    request = urllib.request.Request(endpoint + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "luna-repro/0.3"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(16385)
            if len(raw) > 16384:
                raise PublishError("Connection response exceeds the supported size.")
            return response.status, json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as error:
        code = "authorization_required" if getattr(error, "code", None) in {401, 403} else "transport_error"
        if isinstance(error, urllib.error.HTTPError):
            error.close()
        raise PublishError("Connection was not completed; review access or start a new explicit connection.", code=code) from None


def connect(project, *, endpoint="https://lunalab-ai.com", label=None, timeout=600, open_browser=True, force=False):
    """Approve a project connection in the browser; keep the resulting key in memory.

    A repeated call may reuse an unexpired local pairing. The server still checks
    current access on every publication. force=True explicitly starts a new approval.
    """
    project = str(UUID(str(project)))
    endpoint = _url(endpoint, endpoint=True).rstrip("/")
    if type(timeout) not in {int, float} or not 1 <= timeout <= 600:
        raise ValueError("Connection timeout must be between 1 and 600 seconds.")
    label = label or "Python"
    if label not in {"Python", "Colab", "Jupyter"}:
        raise ValueError("Connection label must be Python, Colab or Jupyter.")
    previous = session.current()
    if not force and previous and previous.project == project and previous.endpoint == endpoint and previous.reusable():
        return {"project_id": project, "project_title": previous.project_title, "expires_at": previous.expires_at, "reused": True}
    secret = secrets.token_urlsafe(32)
    challenge = hashlib.sha256(secret.encode()).hexdigest()
    deadline = time.monotonic() + timeout
    status, start = _post(endpoint, "/api/repro/v1/connect/start/",
        {"project_id": project, "challenge": challenge, "label": label}, min(30, timeout))
    if status != 200 or type(start) is not dict:
        raise PublishError("Unexpected connection approval response.")
    ticket, link = start.get("ticket"), start.get("verification_url")
    origin, destination = urlsplit(endpoint), urlsplit(link or "")
    code = challenge[:8].upper()
    if (type(ticket) is not str or not 1 <= len(ticket) <= 8000 or start.get("user_code") != code
            or (destination.scheme, destination.netloc) != (origin.scheme, origin.netloc)
            or destination.path != "/workspace/repro/connect/approve/" or destination.fragment):
        raise PublishError("Unexpected connection approval destination.")
    interval = start.get("interval", 3)
    if type(interval) not in {int, float} or not 1 <= interval <= 30:
        raise PublishError("Invalid connection polling interval.")
    print("Approve this project connection / 프로젝트 연결 승인:", link)
    print("Confirmation code / 확인 코드:", code)
    if open_browser:
        webbrowser.open(link)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PublishError("Connection approval timed out; no local credential was saved.", code="connection_timeout")
        status, result = _post(endpoint, "/api/repro/v1/connect/claim/", {"ticket": ticket, "secret": secret}, min(30, remaining))
        if status == 200:
            if (type(result) is not dict or result.get("project_id") != project
                    or type(result.get("project_title")) is not str or len(result["project_title"]) > 300
                    or type(result.get("expires_at")) is not str):
                raise PublishError("Connection identity mismatch.")
            token = result.get("token")
            if type(token) is not str or not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
                raise PublishError("Connection key was not returned.")
            if token in result["project_title"] or token in result["expires_at"]:
                raise PublishError("Connection response contains unexpected credential material.")
            configured = session.Configuration(project, endpoint, token,
                previous.outbox if previous and previous.project == project else None,
                result["project_title"], result["expires_at"])
            if not configured.reusable():
                raise PublishError("Connection expiry is invalid.")
            session._configuration.set(configured)
            return {"project_id": project, "project_title": configured.project_title, "expires_at": configured.expires_at, "reused": False}
        if status != 202:
            raise PublishError("Connection was not authorized.", code="authorization_required")
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
