"""Standard-library result collection and explicit HTTPS transport.

This is the result-page protocol, independent of the legacy ReproKit event v1.
Only supplied values/files are serialized. Source links are references, not fetches.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import io
import ipaddress
import json
import math
import numbers
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid

SCHEMA = "luna.repro.page.v1"
MAX_BUNDLE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_SOURCE_KEYS = {"url", "repository_url", "commit", "file", "line_start", "line_end", "cell_id", "snapshot_sha256", "execution_url", "provenance"}
_KEY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")


class PublishError(RuntimeError):
    """Sanitized transport failure: never embeds request, token or remote body."""

    def __init__(self, message, *, code="transport_error", retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def _pending(bundle, error=None):
    result = {"status": "pending", "page_id": bundle["page_id"], "request_id": bundle["request_id"],
        "code": error.code if isinstance(error, PublishError) else "connection_required",
        "message": str(error) if isinstance(error, PublishError) else "Saved locally. Check your endpoint/connection and sync explicitly."}
    if isinstance(error, PublishError) and error.retry_after is not None:
        result["retry_after"] = error.retry_after
    return result


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _uuid(value=None):
    try:
        return str(uuid.UUID(str(value))) if value is not None else str(uuid.uuid4())
    except (ValueError, TypeError, AttributeError):
        raise ValueError("A valid project/page/run UUID is required.") from None


def _text(value, limit=20000, *, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()) or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise ValueError("Text has an invalid type, length or null character.")
    return value


def _url(value, *, endpoint=False):
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        raise ValueError("Use a clean HTTPS URL without credentials or query parameters.")
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        raise ValueError("Invalid URL.") from None
    if not hostname or parsed.username or parsed.password or parsed.query:
        raise ValueError("URLs must not contain credentials or query parameters.")
    loopback = hostname.lower() == "localhost"
    try:
        loopback = loopback or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme != "https" and not (endpoint and parsed.scheme == "http" and loopback):
        raise ValueError("HTTPS is required; HTTP is allowed only for a loopback API endpoint.")
    if endpoint and parsed.fragment:
        raise ValueError("API endpoint must not contain a fragment.")
    if len(value) > 2000:
        raise ValueError("URL is too long.")
    return value


def _source(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - _SOURCE_KEYS:
        raise ValueError("Unsupported source reference fields.")
    result = {}
    for key, item in value.items():
        if item is None:
            continue
        if key == "provenance":
            continue  # Validated after all legacy location fields are available.
        if key in {"url", "repository_url", "execution_url"}:
            result[key] = _url(item)
            parsed = urllib.parse.urlsplit(item)
            if len(item) > 1000 or (parsed.fragment and not re.fullmatch(r"[A-Za-z0-9_=.-]{1,200}", parsed.fragment)):
                raise ValueError("Source URL or fragment exceeds the supported format.")
            decoded = urllib.parse.unquote(urllib.parse.urlunsplit(parsed._replace(fragment="")))
            parts = urllib.parse.urlsplit(decoded)
            host = (parts.hostname or "").rstrip(".").lower()
            if any(ord(c) < 32 or c in '\\<>"' for c in decoded) or parts.username or parts.password or parts.query or parts.fragment or parts.port not in (None, 443):
                raise ValueError("Use a permanent source URL without credentials or encoded control characters.")
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
                raise ValueError("Use a public HTTPS source hostname.")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if (address is not None and not address.is_global) or (address is None and (re.fullmatch(r"[0-9.]+", host) or host.split(".")[-1].isdigit())):
                raise ValueError("Internal source addresses are not supported.")
        elif key in {"line_start", "line_end"}:
            if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 10000000:
                raise ValueError("Source lines must be positive integers.")
            result[key] = item
        elif key in {"commit", "snapshot_sha256"}:
            pattern = r"(?:[a-f0-9]{40}|[a-f0-9]{64})" if key == "commit" else r"[a-f0-9]{64}"
            if item and (not isinstance(item, str) or not re.fullmatch(pattern, item)):
                raise ValueError("Use the exact hexadecimal source checksum/commit.")
            result[key] = item
        elif key == "file":
            result[key] = _text(item, 300)
            path = PurePosixPath(item)
            if "\\" in item or ":" in item or path.is_absolute() or ".." in path.parts:
                raise ValueError("Source file must be a relative repository path.")
        else:
            result[key] = _text(item, 160)
    if result.get("line_end", result.get("line_start", 1)) < result.get("line_start", 1):
        raise ValueError("Source line range is reversed.")
    if "provenance" in value:
        from .source import validate_details
        result["provenance"] = copy.deepcopy(validate_details(value["provenance"], result))
    return result


def _caller_source():
    frame = inspect.currentframe()
    try:
        frame = frame.f_back
        while frame:
            if frame.f_globals.get("__name__") != __name__:
                filename = frame.f_code.co_filename
                if filename.startswith("<"):
                    return {}
                # Do not disclose local home/user paths or inspect source contents.
                return {"file": Path(filename).name, "line_start": frame.f_lineno}
            frame = frame.f_back
        return {}
    finally:
        del frame


def _scalar(value):
    if value is None or isinstance(value, (str, bool)):
        return _text(value, 4000) if isinstance(value, str) else value
    if isinstance(value, numbers.Integral) and abs(value) <= 1e308:
        return int(value)
    if isinstance(value, numbers.Real) and abs(value) <= 1e308 and math.isfinite(float(value)):
        return float(value)
    raise ValueError("Table cells must be JSON scalars with finite numeric values.")


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".luna-repro-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _checked_bundle(bundle):
    """Bounded structural/checksum validation for untrusted outbox files."""
    if not isinstance(bundle, dict) or bundle.get("schema") != SCHEMA:
        raise ValueError("Unsupported result bundle schema.")
    allowed = {"schema", "project_id", "page_id", "run_id", "request_id", "title", "description", "metadata", "evidence", "source", "sections", "artifacts"}
    if set(bundle) - allowed:
        raise ValueError("Unsupported bundle fields; credentials do not belong in a bundle.")
    for key in ("project_id", "page_id", "run_id", "request_id"):
        _uuid(bundle.get(key) or "invalid")
    _text(bundle.get("title"), 300, required=True)
    _text(bundle.get("description", ""), 12000)
    _source(bundle.get("source"))
    metadata = bundle.get("metadata", {})
    if not isinstance(metadata, dict) or set(metadata) - {"tags"}:
        raise ValueError("Metadata supports tags only.")
    tags = metadata.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 30:
        raise ValueError("At most 30 tags are allowed.")
    for tag in tags:
        _text(tag, 100, required=True)
    evidence = bundle.get("evidence", {})
    if not isinstance(evidence, dict) or set(evidence) - {"origin", "execution_status", "evaluation_status"}:
        raise ValueError("Unsupported evidence fields.")
    if evidence.get("origin") not in {"imported", "executed", "synthetic"} or evidence.get("execution_status") not in {"unknown", "completed", "failed"} or evidence.get("evaluation_status") not in {"not_run", "completed"}:
        raise ValueError("Invalid evidence status.")
    artifacts = bundle.get("artifacts", [])
    if not isinstance(artifacts, list) or len(artifacts) > 100:
        raise ValueError("Too many artifacts.")
    artifact_ids = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"sha256", "name", "mime", "data_base64"}:
            raise ValueError("Invalid image artifact.")
        if not isinstance(artifact["data_base64"], str) or len(artifact["data_base64"]) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
            raise ValueError("Image encoding exceeds the size limit.")
        try:
            data = base64.b64decode(artifact["data_base64"], validate=True)
        except (ValueError, TypeError):
            raise ValueError("Invalid image encoding.") from None
        digest = hashlib.sha256(data).hexdigest()
        if digest != artifact["sha256"] or digest in artifact_ids:
            raise ValueError("Image checksum mismatch or duplicate artifact.")
        if _image_mime(data) != artifact["mime"]:
            raise ValueError("Image type does not match its bytes.")
        name = _text(artifact["name"], 160, required=True)
        if name != PurePosixPath(name).name or "\\" in name or ":" in name:
            raise ValueError("Image name must be a plain file name.")
        artifact_ids.add(digest)
    sections = bundle.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 100:
        raise ValueError("A page needs 1 to 100 sections.")
    seen, count = set(), 0
    used_artifacts = set()
    for section in sections:
        if not isinstance(section, dict) or set(section) - {"key", "title", "description", "source", "blocks"}:
            raise ValueError("Invalid section.")
        key = section.get("key")
        if not isinstance(key, str) or not _KEY.fullmatch(key) or key in seen:
            raise ValueError("Section keys must be unique, stable ASCII identifiers.")
        seen.add(key)
        _text(section.get("title"), 300, required=True)
        _text(section.get("description", ""), 12000)
        _source(section.get("source"))
        blocks = section.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ValueError("A section must contain at least one block.")
        count += len(blocks)
        for block in blocks:
            if not isinstance(block, dict):
                raise ValueError("Invalid result block.")
            kind = block.get("kind")
            if kind == "text" and set(block) == {"kind", "text"}:
                _text(block["text"])
            elif kind == "metrics" and set(block) == {"kind", "values"}:
                _metrics(block["values"])
            elif kind == "table" and set(block) == {"kind", "columns", "rows"}:
                _table(block["columns"], block["rows"])
            elif kind == "image" and set(block) == {"kind", "sha256", "caption"}:
                if block["sha256"] not in artifact_ids:
                    raise ValueError("Image reference has no artifact.")
                used_artifacts.add(block["sha256"])
                _text(block["caption"], 2000)
            else:
                raise ValueError("Unsupported result block.")
    if count > 500 or used_artifacts != artifact_ids:
        raise ValueError("Too many blocks or unreferenced artifacts.")
    from .source import snapshot_bytes
    snapshot_bytes([bundle.get("source", {}), *(section.get("source", {}) for section in sections)])
    data = _json(bundle)
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError("Result bundle exceeds the 16 MiB limit.")
    return data


def _metrics(values):
    if not isinstance(values, dict) or not values or len(values) > 100:
        raise ValueError("Metrics need 1 to 100 named numeric values.")
    result = {}
    for key, value in values.items():
        _text(key, 160, required=True)
        if isinstance(value, bool) or not isinstance(value, numbers.Real) or abs(value) > 1e308 or not math.isfinite(float(value)):
            raise ValueError("Metrics must contain finite numbers only.")
        result[key] = int(value) if isinstance(value, numbers.Integral) else float(value)
    return result


def _table(columns, rows):
    if not isinstance(columns, (list, tuple)) or not 1 <= len(columns) <= 100:
        raise ValueError("A table needs 1 to 100 columns.")
    columns = [_text(column, 160, required=True) for column in columns]
    if not isinstance(rows, (list, tuple)) or len(rows) > 2000:
        raise ValueError("A table supports at most 2000 rows.")
    result = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != len(columns):
            raise ValueError("Each table row must match its columns.")
        result.append([_scalar(cell) for cell in row])
    return columns, result


def _image_mime(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("An image must be at most 8 MiB.")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33:
        return "image/png"
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "image/jpeg"
    raise ValueError("Only PNG and JPEG images are supported.")


class Section:
    def __init__(self, page, data):
        self._page, self._data = page, data

    def text(self, text):
        self._data["blocks"].append({"kind": "text", "text": _text(text)})
        return self

    def metrics(self, values):
        self._data["blocks"].append({"kind": "metrics", "values": _metrics(values)})
        return self

    def table(self, columns, rows=None):
        """Accept columns+rows or a dataframe with columns/itertuples; never eval."""
        if rows is None and hasattr(columns, "columns") and hasattr(columns, "itertuples"):
            frame = columns
            if len(frame) > 2000 or len(frame.columns) > 100:
                raise ValueError("Dataframe exceeds table limits.")
            columns, rows = [str(c) for c in frame.columns], list(frame.itertuples(index=False, name=None))
        names, values = _table(columns, rows)
        self._data["blocks"].append({"kind": "table", "columns": names, "rows": values})
        return self

    def image(self, path_or_bytes, caption="", *, name=None):
        if isinstance(path_or_bytes, (bytes, bytearray)):
            data = bytes(path_or_bytes)
            name = name or "result.png"
        else:
            path = Path(path_or_bytes)
            if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError("Select one PNG/JPEG file of at most 8 MiB.")
            with path.open("rb") as stream:
                data = stream.read(MAX_IMAGE_BYTES + 1)
            name = name or path.name
        mime = _image_mime(data)
        digest = hashlib.sha256(data).hexdigest()
        encoded_size = (len(data) + 2) // 3 * 4
        existing_size = sum(len(item["data_base64"]) for key, item in self._page._artifacts.items() if key != digest)
        if existing_size + encoded_size > MAX_BUNDLE_BYTES:
            raise ValueError("Selected images exceed the 16 MiB bundle limit; split the result page.")
        self._page._artifacts[digest] = {"sha256": digest, "name": _text(Path(name).name, 160, required=True), "mime": mime, "data_base64": base64.b64encode(data).decode("ascii")}
        self._data["blocks"].append({"kind": "image", "sha256": digest, "caption": _text(caption, 2000)})
        return self

    def figure(self, figure, caption=""):
        """Export an explicitly supplied matplotlib figure, or a PNG/JPEG path."""
        if hasattr(figure, "savefig"):
            output = io.BytesIO()
            figure.savefig(output, format="png", bbox_inches="tight")
            return self.image(output.getvalue(), caption, name="figure.png")
        return self.image(figure, caption)

    chart = figure


class Page:
    def __init__(self, project, title, *, description="", endpoint=None, token=None, page_id=None, run_id=None, metadata=None, evidence=None, source=None, outbox=None):
        self.project_id, self.page_id, self.run_id = _uuid(project), _uuid(page_id), _uuid(run_id)
        self.title, self.description = _text(title, 300, required=True), _text(description, 12000)
        self.metadata = copy.deepcopy(metadata or {"tags": []})
        self.evidence = {"origin": "imported", "execution_status": "unknown", "evaluation_status": "not_run", **(evidence or {})}
        self.source = _source(source)
        self.endpoint = endpoint
        self._token = token
        self.outbox = Path(outbox) if outbox is not None else Path(".luna-repro") / "outbox"
        self._sections, self._artifacts = {}, {}
        self._content_hash, self._request_id = None, None

    def section(self, key, title=None, *, description="", source=None):
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ValueError("Use a stable ASCII section key up to 80 characters (letters, numbers, dash or underscore).")
        if key in self._sections:
            section = self._sections[key]
            if title is not None:
                section._data["title"] = _text(title, 300, required=True)
            if source is not None:
                section._data["source"] = _source(source)
            return section
        # A declared computation source takes precedence over the registration
        # call site. Keep these identities separate; never merge file/line/commit.
        selected_source = _source(source) if source is not None else copy.deepcopy(self.source) if self.source else _caller_source()
        data = {"key": key, "title": _text(title or key, 300, required=True), "description": _text(description, 12000), "source": selected_source, "blocks": []}
        section = Section(self, data)
        self._sections[key] = section
        return section

    def bundle(self):
        result = {"schema": SCHEMA, "project_id": self.project_id, "page_id": self.page_id, "run_id": self.run_id, "title": self.title, "description": self.description, "metadata": self.metadata, "evidence": self.evidence, "source": self.source, "sections": [section._data for section in self._sections.values()], "artifacts": list(self._artifacts.values())}
        serialized = _json(result)
        # Protect configured bearer tokens even when accidentally selected as text.
        for secret in (self._token, os.environ.get("LUNA_REPRO_TOKEN")):
            if secret and str(secret).encode("utf-8") in serialized:
                raise ValueError("A configured credential appears in selected results; remove it before saving.")
        digest = hashlib.sha256(serialized).hexdigest()
        if digest != self._content_hash:
            self._content_hash, self._request_id = digest, _uuid()
        result["request_id"] = self._request_id
        _checked_bundle(result)
        return copy.deepcopy(result)

    def save(self, path):
        """Save only selected data plus identities; no token or endpoint is stored."""
        return _atomic_write(path, _checked_bundle(self.bundle()))

    def publish(self, *, endpoint=None, token=None, strict=False, timeout=30):
        bundle = self.bundle()
        data = _checked_bundle(bundle)
        if token and str(token).encode("utf-8") in data:
            raise ValueError("A configured credential appears in selected results; remove it before saving.")
        pending = self.outbox / (bundle["request_id"] + ".json")
        _atomic_write(pending, data)
        try:
            receipt = publish_bundle(bundle, endpoint=endpoint or self.endpoint, token=token or self._token, timeout=timeout)
        except (PublishError, ValueError) as error:
            if strict:
                raise
            return {**_pending(bundle, error), "outbox_path": str(pending)}
        # Successful receipts and originals remain available; no automatic deletion.
        _atomic_write(self.outbox / (bundle["request_id"] + ".receipt.json"), _json(receipt))
        return receipt


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        raise PublishError("API redirects are refused; use the final HTTPS endpoint.")


def publish_bundle(bundle, *, endpoint=None, token=None, timeout=30):
    data = _checked_bundle(bundle)
    endpoint = _url(endpoint or os.environ.get("LUNA_REPRO_ENDPOINT", ""), endpoint=True).rstrip("/")
    token = token or os.environ.get("LUNA_REPRO_TOKEN", "")
    if not isinstance(token, str) or not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ValueError("Set a valid project-scoped LUNA_REPRO_TOKEN in this session.")
    if token.encode() in data:
        raise ValueError("A configured credential appears in selected results.")
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
        raise ValueError("Timeout must be between 0 and 120 seconds.")
    url = endpoint if endpoint.endswith("/api/repro/v1/pages") else endpoint + "/api/repro/v1/pages"
    request = urllib.request.Request(url + "/", data=data, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "luna-repro/0.1"}, method="POST")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise PublishError("API receipt exceeds the size limit.")
        result = json.loads(raw)
    except urllib.error.HTTPError as exc:
        code = exc.code
        known = {
            "storage_quota": "Project result storage quota reached. Review the storage policy before an explicit retry.",
            "rate_limited": "Request limit reached. Wait for the indicated interval, then sync explicitly.",
            "authorization_required": "Project authorization is missing, expired or revoked. Check your session token and current access.",
            "request_conflict": "This saved request conflicts with an existing receipt. Check the result identity before sending a new revision.",
            "page_conflict": "This page identity cannot be used for the selected project or account.",
            "version_limit": "This result page reached its revision limit. Start a new explicitly linked page.",
            "result_trashed": "This result is in Trash. Restore it in the platform before an explicit retry. The local bundle is preserved; nothing was restored automatically.",
            "invalid_source_snapshot": "Selected source text, location or checksum is invalid. Check the bounded source selection before publishing.",
            "source_snapshot_limit": "Selected code snapshots exceed the page limit. Select less code before publishing; the local bundle is preserved.",
        }
        reason, retry_after = "request_rejected", None
        try:
            raw_error = exc.read(65537)
            if len(raw_error) <= 65536:
                detail = json.loads(raw_error)
                if isinstance(detail, dict) and isinstance(detail.get("error"), str) and detail["error"] in known:
                    reason = detail["error"]
            raw_retry = exc.headers.get("Retry-After", "")
            if raw_retry.isdecimal() and len(raw_retry) <= 6 and 0 <= int(raw_retry) <= 86400:
                retry_after = int(raw_retry)
        except (ValueError, OSError, TypeError):
            pass
        finally:
            exc.close()
        if reason == "request_rejected" and code == 429:
            reason = "rate_limited"
        message = known.get(reason, "API rejected the result (HTTP %d). The local bundle is preserved." % code)
        raise PublishError(message, code=reason, retry_after=retry_after) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise PublishError("No valid API receipt received. The local bundle is preserved.") from None
    if not isinstance(result, dict) or result.get("page_id") != bundle["page_id"] or isinstance(result.get("revision"), bool) or not isinstance(result.get("revision"), int) or result["revision"] < 1:
        raise PublishError("API receipt identity or revision is invalid.")
    # Store only safe known receipt fields. Never persist raw server response.
    try:
        receipt_url = _url(result.get("url"), endpoint=True)
    except ValueError:
        raise PublishError("API receipt URL is invalid.") from None
    receipt_origin, api_origin = urllib.parse.urlsplit(receipt_url), urllib.parse.urlsplit(endpoint)
    if (receipt_origin.scheme, receipt_origin.netloc) != (api_origin.scheme, api_origin.netloc):
        raise PublishError("API receipt must link to the same platform.")
    if token in receipt_url:
        raise PublishError("API receipt contains credential material and was refused.")
    return {"status": "published", "page_id": bundle["page_id"], "request_id": bundle["request_id"], "revision": result["revision"], "url": receipt_url}


def load_bundle(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Select a result JSON file of at most 16 MiB.")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_BUNDLE_BYTES + 1)
        if len(data) > MAX_BUNDLE_BYTES:
            raise ValueError
        bundle = json.loads(data)
        _checked_bundle(bundle)
    except (ValueError, TypeError, KeyError):
        raise ValueError("Invalid result bundle or image checksum.") from None
    return bundle


def sync(outbox=".luna-repro/outbox", *, endpoint=None, token=None, timeout=30):
    """Explicit retry of pending JSONs; receipts cause successful jobs to be skipped."""
    outcomes = []
    for path in sorted(Path(outbox).glob("*.json")):
        if path.name.endswith(".receipt.json") or path.with_suffix(".receipt.json").exists():
            continue
        bundle = load_bundle(path)
        try:
            receipt = publish_bundle(bundle, endpoint=endpoint, token=token, timeout=timeout)
        except (PublishError, ValueError) as error:
            outcomes.append(_pending(bundle, error))
            continue
        _atomic_write(path.with_suffix(".receipt.json"), _json(receipt))
        outcomes.append(receipt)
    return outcomes
