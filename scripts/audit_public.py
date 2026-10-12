"""Fail closed on unreviewed release files and obvious private material."""
import hashlib
import json
from pathlib import Path
import re
import sys

from release_spec import ROOT, PUBLIC, VERSION

UUID = re.compile(r"(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b")
SYNTHETIC_IDS = {"12345678-1234-5678-1234-567812345678", "12345678-1234-5678-1234-567812345679"}
PRIVATE = re.compile(r"(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|sk-proj-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
LOCAL_USER = re.compile(r"(?i)(?:[a-z]:[\\/]+Users[\\/]+(?!YOUR|USER|EXAMPLE)|/home/(?!YOUR|USER|EXAMPLE))[a-z0-9_.-]+")
IGNORED_DIRS = {".git", ".venv", ".build", "dist", "build", "__pycache__"}


def audit(root=ROOT):
    root = Path(root)
    found = set()
    def scan(path):
        for child in path.iterdir():
            if child.name in IGNORED_DIRS or child.name.endswith(".egg-info"):
                continue
            if child.is_symlink():
                raise ValueError("Public source must not contain symlinks")
            if child.is_dir():
                scan(child)
            else:
                found.add(child.relative_to(root).as_posix())
    scan(root)
    if found != set(PUBLIC):
        raise ValueError("Public file allowlist mismatch: " + repr(sorted(found ^ set(PUBLIC))))
    hashes = {}
    for name in PUBLIC:
        data = (root / name).read_bytes()
        if len(data) > 500_000:
            raise ValueError("Public source file exceeds audit limit: " + name)
        text = data.decode("utf-8")
        if PRIVATE.search(text) or LOCAL_USER.search(text):
            raise ValueError("Potential private material in " + name)
        if set(UUID.findall(text)) - SYNTHETIC_IDS:
            raise ValueError("Unreviewed project identifier in " + name)
        if name.endswith(".ipynb"):
            value = json.loads(text)
            for cell in value["cells"]:
                if cell.get("attachments") or cell.get("outputs") or cell.get("execution_count") is not None:
                    raise ValueError("Notebook is not clean: " + name)
                if cell["cell_type"] == "code":
                    compile("".join(cell["source"]), name, "exec")
        hashes[name] = hashlib.sha256(data).hexdigest()
    if f'version = "{VERSION}"' not in (root / "pyproject.toml").read_text(encoding="utf-8"):
        raise ValueError("Package version mismatch")
    if f'__version__ = "{VERSION}"' not in (root / "luna_repro/__init__.py").read_text(encoding="utf-8"):
        raise ValueError("Runtime version mismatch")
    return {"status": "passed", "files": len(hashes), "source_sha256": hashes}


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, sort_keys=True))
