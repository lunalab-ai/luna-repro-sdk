"""Install release artifacts in new isolated environments; use synthetic inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import venv
import zipfile

from audit_public import audit
from release_spec import ROOT, VERSION, LEGACY, PREFIX


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", default="dist")
    parser.add_argument("--build-tools", required=True, help="Local wheel directory for setuptools 80.9.0 and wheel 0.45.1")
    args = parser.parse_args(argv)
    before = audit()
    assets, build_tools = Path(args.artifacts).resolve(), Path(args.build_tools).resolve()
    manifest = json.loads((assets / "release-manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["artifacts"].items():
        data = (assets / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"] and len(data) == entry["size"]
    run = ROOT / ".build" / ("validation-" + uuid.uuid4().hex)
    run.mkdir(parents=True)
    result = {"status": "running", "version": VERSION, "source_before": before, "checks": [], "network": "local artifact installs only"}
    env = {key: value for key, value in os.environ.items() if not key.startswith("LUNA_") and key != "PYTHONPATH"}
    def command(label, args, cwd):
        completed = subprocess.run([str(item) for item in args], cwd=cwd, env=env, capture_output=True, timeout=240)
        (run / (label + ".log")).write_bytes(completed.stdout + completed.stderr)
        result["checks"].append({"label": label, "returncode": completed.returncode})
        if completed.returncode:
            raise RuntimeError(label + " failed; see isolated validation log")
    try:
        extracted = run / "extracted"
        with zipfile.ZipFile(assets / f"luna-repro-sdk-{VERSION}.zip") as archive:
            assert archive.namelist() == [PREFIX + name for name in sorted(LEGACY)]
            for name in LEGACY:
                target = extracted / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(PREFIX + name))
        for kind, filename in (("wheel", f"luna_repro-{VERSION}-py3-none-any.whl"), ("zip", f"luna-repro-sdk-{VERSION}.zip")):
            folder = run / kind
            venv.EnvBuilder(with_pip=True).create(folder)
            python = folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if kind == "zip":
                command(kind + "-build-tools", [python, "-m", "pip", "install", "--no-index", "--find-links", build_tools, "setuptools==80.9.0", "wheel==0.45.1"], folder)
            command(kind + "-install", [python, "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation", assets / filename], folder)
            command(kind + "-import", [python, "-I", "-c", "import luna_repro, pathlib, sys; assert luna_repro.__version__ == '0.3.0'; assert pathlib.Path(luna_repro.__file__).is_relative_to(pathlib.Path(sys.prefix)); print(luna_repro.__version__)"], folder)
            command(kind + "-cli", [python, "-I", "-m", "luna_repro", "--help"], folder)
            command(kind + "-walkthrough", [python, "-I", extracted / "examples/walkthrough.py", "--include-source"], folder)
            command(kind + "-toy", [python, "-I", extracted / "examples/toy.py", "--project", "12345678-1234-5678-1234-567812345678"], folder)
            command(kind + "-selection", [python, "-I", extracted / "examples/auto_select.py"], folder)
            # Run every default cell with the installed package and networking blocked.
            code = "import contextlib,io,json,pathlib,socket; from unittest.mock import patch; paths=pathlib.Path(%r).glob('*.ipynb');\nwith patch('socket.create_connection', side_effect=AssertionError('No network')):\n for path in paths:\n  scope={'__name__':'__main__'}\n  for cell in json.loads(path.read_text(encoding='utf-8'))['cells']:\n   if cell['cell_type']=='code':\n    with contextlib.redirect_stdout(io.StringIO()): exec(compile(''.join(cell['source']),str(path),'exec'),scope)\nprint('All notebook code cells completed offline')" % str(extracted / "examples")
            command(kind + "-notebooks", [python, "-I", "-c", code], folder)
            command(kind + "-pip-check", [python, "-m", "pip", "check"], folder)
        after = audit()
        assert before == after
        result.update(status="passed", source_after=after, source_unchanged=True)
    except Exception:
        result["status"] = "failed"
        raise
    finally:
        (run / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"receipt": str(run / "result.json"), "status": result["status"], "checks": len(result["checks"])}))


if __name__ == "__main__":
    main()
