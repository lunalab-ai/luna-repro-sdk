"""Build immutable local artifacts twice; never publish or access the network."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from audit_public import audit
from release_spec import ROOT, PUBLIC, RUNTIME, LEGACY, GUIDES, VERSION, EPOCH, ZIP_TIME, PREFIX


def zip_bytes(root, members, prefix):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            item = zipfile.ZipInfo(prefix + name, ZIP_TIME)
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            item.compress_type = zipfile.ZIP_STORED
            archive.writestr(item, (root / name).read_bytes())
    return output.getvalue()


def normalized_sdist(path):
    """Setuptools supplies content; normalize tar/gzip metadata deterministically."""
    raw = io.BytesIO()
    with tarfile.open(path, "r:gz") as original, tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as target:
        for entry in sorted(original.getmembers(), key=lambda item: item.name):
            if not entry.isfile():
                continue
            if entry.name.startswith("/") or ".." in Path(entry.name).parts:
                raise ValueError("Invalid sdist path")
            data = original.extractfile(entry).read()
            member = tarfile.TarInfo(entry.name)
            member.size, member.mtime, member.mode = len(data), EPOCH, 0o644
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            target.addfile(member, io.BytesIO(data))
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=EPOCH, compresslevel=9) as stream:
        stream.write(raw.getvalue())
    return output.getvalue()


def build_once():
    with tempfile.TemporaryDirectory(prefix="luna-sdk-build-") as folder:
        root = Path(folder) / "source"
        root.mkdir()
        for name in PUBLIC:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        # sdist contents are explicit; generated setuptools metadata is public.
        (root / "MANIFEST.in").write_text("\n".join("include " + name for name in PUBLIC) + "\n", encoding="utf-8")
        output = Path(folder) / "output"
        output.mkdir()
        env = {**os.environ, "SOURCE_DATE_EPOCH": str(EPOCH), "PYTHONHASHSEED": "0"}
        code = "import importlib.metadata as m; assert m.version('setuptools')=='80.9.0'; assert m.version('wheel')=='0.45.1'; import setuptools.build_meta as b; b.build_wheel(%r); b.build_sdist(%r)" % (str(output), str(output))
        result = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True, timeout=120)
        if result.returncode:
            raise RuntimeError("Build failed: " + result.stderr.decode("utf-8", errors="replace")[-3000:])
        wheel = output / f"luna_repro-{VERSION}-py3-none-any.whl"
        sdist = output / f"luna_repro-{VERSION}.tar.gz"
        return {wheel.name: wheel.read_bytes(), sdist.name: normalized_sdist(sdist),
                f"luna-repro-sdk-{VERSION}.zip": zip_bytes(ROOT, LEGACY, PREFIX),
                f"luna-repro-sdk-guides-{VERSION}.zip": zip_bytes(ROOT, GUIDES, "luna-repro-sdk-guides/")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dist")
    args = parser.parse_args(argv)
    before = audit()
    first, second = build_once(), build_once()
    if first != second or audit() != before:
        raise ValueError("Non-deterministic artifacts or source changed during build")
    artifact_info = {name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for name, data in sorted(first.items())}
    manifest = {"schema": "luna.repro.sdk.release.v1", "version": VERSION,
                "package": "luna-repro", "python_requires": ">=3.10", "protocol": "luna.repro.page.v1",
                "source_protocol": "luna.repro.source.v1", "deterministic_rebuild": True,
                "build_tools": {"setuptools": "80.9.0", "wheel": "0.45.1"},
                "artifacts": artifact_info,
                "legacy": {"filename": f"luna-repro-sdk-{VERSION}.zip", "prefix": PREFIX,
                           "members": {name: before["source_sha256"][name] for name in LEGACY},
                           "timestamp": list(ZIP_TIME), "compression": "ZIP_STORED", "mode": "100644"},
                "source_sha256": before["source_sha256"]}
    first["release-manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    first["SHA256SUMS"] = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in sorted(first.items())).encode()
    destination = Path(args.output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(first.items()):
        path = destination / name
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("Refusing to overwrite a different release artifact: " + name)
        else:
            with path.open("xb") as stream:
                stream.write(data)
    print(json.dumps({"status": "passed", "deterministic_rebuild": True, "directory": str(destination), "artifacts": artifact_info}, sort_keys=True))


if __name__ == "__main__":
    main()
