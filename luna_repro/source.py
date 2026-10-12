"""Explicit source selection. Never crawls directories, executes code or uploads.

Metadata helpers only read the selected file and bounded local Git metadata.
Source text is included only when snapshot=True. An identity match is a producer
observation, not independent scientific verification or proof of execution.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

SCHEMA = "luna.repro.source.v1"
MAX_SNAPSHOT_BYTES = 32768
MAX_SOURCE_BYTES = 1024 * 1024
MAX_PAGE_SNAPSHOT_BYTES = 262144
MAX_SNAPSHOT_LINES = 1000


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def validate_details(value, reference):
    """Validate the opt-in versioned extension, shared with platform intake."""
    allowed = {"schema", "role", "provider", "symbol", "dirty", "commit_match",
               "file_sha256", "cell_namespace", "cell_sha256", "snapshot"}
    if not isinstance(value, dict) or set(value) - allowed or value.get("schema") != SCHEMA:
        raise ValueError("Unsupported source provenance schema or fields.")
    if value.get("role") not in {"registration", "computation", "definition", "reference"}:
        raise ValueError("Choose a source role: registration, computation, definition or reference.")
    if value.get("provider") not in {"python", "jupyter", "colab"}:
        raise ValueError("Unsupported source provider.")
    if "symbol" in value and (not isinstance(value["symbol"], str) or len(value["symbol"]) > 200
                              or any(ord(c) < 32 for c in value["symbol"])):
        raise ValueError("Invalid source symbol.")
    for key in ("dirty", "commit_match"):
        if key in value and value[key] is not None and type(value[key]) is not bool:
            raise ValueError("Source identity observations must be boolean or unknown.")
    for key in ("file_sha256", "cell_sha256"):
        if key in value and (not isinstance(value[key], str) or not re.fullmatch(r"[a-f0-9]{64}", value[key])):
            raise ValueError("Invalid source digest.")
    if value.get("commit_match") is True and (value.get("dirty") is not False or not reference.get("commit")):
        raise ValueError("A commit match needs a clean source and exact commit.")
    if value.get("cell_namespace") not in (None, "nbformat", "colab"):
        raise ValueError("Unknown notebook cell identity namespace.")
    if value.get("provider") in {"jupyter", "colab"}:
        if not reference.get("cell_id") or not value.get("cell_namespace"):
            raise ValueError("Notebook provenance needs an explicit cell identity and namespace.")
        if value["provider"] == "colab" and value["cell_namespace"] != "colab":
            raise ValueError("Colab navigation needs its actual provider cell identity.")
        if value["provider"] == "jupyter" and value["cell_namespace"] != "nbformat":
            raise ValueError("Jupyter cells need the notebook's actual nbformat identity.")
    elif "cell_namespace" in value or "cell_sha256" in value:
        raise ValueError("Python file provenance cannot claim a notebook cell.")
    snapshot = value.get("snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, dict) or set(snapshot) != {"text", "sha256", "start_line", "scope"}:
            raise ValueError("Invalid selected source snapshot.")
        content = snapshot["text"]
        if not isinstance(content, str) or not content or any(ord(c) < 32 and c not in "\n\r\t" for c in content):
            raise ValueError("Source snapshots contain plain selected UTF-8 text only.")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_SNAPSHOT_BYTES or len(content.splitlines()) > MAX_SNAPSHOT_LINES:
            raise ValueError("Select at most 32 KiB and 1000 lines of source per reference.")
        if snapshot["sha256"] != _hash(encoded) or reference.get("snapshot_sha256") != snapshot["sha256"]:
            raise ValueError("Source snapshot checksum does not match selected text.")
        start = snapshot["start_line"]
        if type(start) is not int or not 1 <= start <= 10000000 or snapshot["scope"] not in {"file", "selection", "cell"}:
            raise ValueError("Invalid snapshot location or scope.")
        end = start + len(content.splitlines()) - 1
        if reference.get("line_start", start) < start or reference.get("line_end", reference.get("line_start", start)) > end:
            raise ValueError("Selected source lines fall outside the preserved snapshot.")
        if snapshot["scope"] == "cell" and (start != 1 or value["provider"] == "python"
                                             or value.get("cell_sha256") != snapshot["sha256"]):
            raise ValueError("Cell snapshots use cell-local line numbers.")
    return value


def snapshot_bytes(references):
    total = sum(len(ref.get("provenance", {}).get("snapshot", {}).get("text", "").encode("utf-8")) for ref in references)
    if total > MAX_PAGE_SNAPSHOT_BYTES:
        raise ValueError("Selected code snapshots exceed the 256 KiB page limit.")
    return total


def _selected(path, root):
    path = Path(path).resolve(strict=True)
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or not path.is_file() or not path.is_relative_to(root) or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Select one existing source file of at most 1 MiB inside the declared root.")
    with path.open('rb') as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("Selected source file exceeds 1 MiB.")
    return path, root, raw


def _git(root, args):
    # No shell, network, hooks, submodule update or arbitrary user command.
    try:
        result = subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 and len(result.stdout) <= MAX_SOURCE_BYTES else None


def _identity(path, root, raw, repository_url):
    result = {"file": path.relative_to(root).as_posix()}
    detail = {"schema": SCHEMA, "role": "computation", "provider": "python",
              "file_sha256": _hash(raw), "dirty": None, "commit_match": None}
    top = _git(root, ["rev-parse", "--show-toplevel"])
    if top is not None:
        git_root = Path(top.decode("utf-8", errors="strict").strip()).resolve()
        if git_root == root:
            head = _git(root, ["rev-parse", "HEAD"])
            commit = head.decode("ascii").strip() if head else ""
            if re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", commit):
                result["commit"] = commit
                object_name = commit + ":" + result["file"]
                size = _git(root, ["cat-file", "-s", object_name])
                committed = (_git(root, ["show", object_name])
                             if size and size.strip().isdigit() and int(size) <= MAX_SOURCE_BYTES else None)
                detail["commit_match"] = committed is not None and committed == raw
                detail["dirty"] = not detail["commit_match"]
    if repository_url:
        result["repository_url"] = repository_url
    result["provenance"] = detail
    return result


def _range(text, start, end):
    lines = text.splitlines(keepends=True)
    end = len(lines) if end is None else end
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
        raise ValueError("Selected line range does not exist in the source file.")
    return "".join(lines[start - 1:end]), end


def _snapshot(reference, text, start, scope):
    digest = _hash(text.encode("utf-8"))
    reference["snapshot_sha256"] = digest
    reference["provenance"]["snapshot"] = {"text": text, "sha256": digest, "start_line": start, "scope": scope}


def _finish(reference):
    from .client import _source
    # Only an observed exact file/commit match yields an automatic pinned URL.
    detail = reference["provenance"]
    repository = reference.get("repository_url", "").rstrip("/")
    if repository.endswith(".git"):
        repository = repository[:-4]
    if detail.get("commit_match") is True and repository:
        parts = urlsplit(repository)
        if parts.hostname == "github.com" and re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", parts.path):
            from urllib.parse import quote
            path = quote(reference["file"], safe="/")
            reference["url"] = repository + "/blob/" + reference["commit"] + "/" + path
            if detail["provider"] == "python":
                reference["url"] += "#L" + str(reference["line_start"]) + "-L" + str(reference["line_end"])
    return _source(reference)


def file(path, *, root, line_start=1, line_end=None, snapshot=False, repository_url=None, role="computation"):
    """Select an existing Python text file/range. Code inclusion is opt-in."""
    path, root, raw = _selected(path, root)
    if path.suffix != ".py":
        raise ValueError("Use source.notebook for .ipynb files; file() selects .py source.")
    text, end = _range(raw.decode("utf-8-sig"), line_start, line_end)
    reference = _identity(path, root, raw, repository_url)
    reference.update(line_start=line_start, line_end=end)
    reference["provenance"]["role"] = role
    if snapshot:
        _snapshot(reference, text, line_start, "file" if line_start == 1 and line_end is None else "selection")
    return _finish(reference)


def function(function, *, root, snapshot=False, repository_url=None):
    """Select a function/class definition; does not claim it was executed."""
    try:
        lines, start = inspect.getsourcelines(function)
        filename = inspect.getsourcefile(function)
    except (OSError, TypeError):
        raise ValueError("Definition source is unavailable; select the actual file/cell explicitly.") from None
    if not filename:
        raise ValueError("Definition has no accessible source file.")
    reference = file(filename, root=root, line_start=start, line_end=start + len(lines) - 1,
                     snapshot=snapshot, repository_url=repository_url, role="definition")
    reference["provenance"]["symbol"] = getattr(function, "__qualname__", getattr(function, "__name__", ""))
    return _finish(reference)


def registration(*, root, snapshot=False, repository_url=None):
    """Explicitly capture this call's registration location, never earlier computation."""
    frame = inspect.currentframe().f_back
    try:
        return file(frame.f_code.co_filename, root=root, line_start=frame.f_lineno,
                    line_end=frame.f_lineno, snapshot=snapshot,
                    repository_url=repository_url, role="registration")
    finally:
        del frame


def notebook(path, cell_id, *, root, provider="jupyter", notebook_url=None, snapshot=False, repository_url=None, role="definition"):
    """Select one saved cell by nbformat ID or actual Colab metadata.id.

    Reads one bounded saved notebook; never outputs/attachments. It does not guess
    which cell is running or claim that a saved file is identical to live memory.
    """
    path, root, raw = _selected(path, root)
    if path.suffix != ".ipynb" or provider not in {"jupyter", "colab"}:
        raise ValueError("Select a saved .ipynb and a supported notebook provider.")
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Notebook JSON must not contain duplicate keys.")
            result[key] = value
        return result

    try:
        data = json.loads(raw, object_pairs_hook=unique_keys)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Select a valid UTF-8 notebook JSON document with bounded nesting.") from exc
    cells = data.get("cells") if isinstance(data, dict) else None
    if not isinstance(cells, list) or len(cells) > 1000:
        raise ValueError("Invalid or oversized notebook cell list.")
    if not isinstance(cell_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cell_id):
        raise ValueError("Use an actual stable cell ID, not its position or execution count.")
    matches = [cell for cell in cells if isinstance(cell, dict) and
               (cell.get("metadata", {}).get("id") if provider == "colab" and isinstance(cell.get("metadata", {}), dict)
                else cell.get("id") if provider == "jupyter" else None) == cell_id]
    if len(matches) != 1 or matches[0].get("cell_type") != "code":
        raise ValueError("The selected code cell identity is missing or duplicated in this provider namespace.")
    content = matches[0].get("source")
    if isinstance(content, list) and all(isinstance(line, str) for line in content):
        content = "".join(content)
    if not isinstance(content, str) or not content:
        raise ValueError("The selected cell has no source text.")
    reference = _identity(path, root, raw, repository_url)
    reference.update(cell_id=cell_id, line_start=1, line_end=len(content.splitlines()))
    reference["provenance"].update(provider=provider, role=role,
                                   cell_namespace="colab" if provider == "colab" else "nbformat",
                                   cell_sha256=_hash(content.encode("utf-8")))
    if snapshot:
        _snapshot(reference, content, 1, "cell")
    reference = _finish(reference)
    if notebook_url:
        reference["execution_url"] = notebook_url
        if provider == "colab":
            parts = urlsplit(notebook_url)
            if parts.hostname != "colab.research.google.com" or parts.query or parts.fragment:
                raise ValueError("Use the clean Colab notebook URL; cell navigation comes from its metadata ID.")
            reference["url"] = notebook_url + "#scrollTo=" + cell_id
    from .client import _source
    return _source(reference)
