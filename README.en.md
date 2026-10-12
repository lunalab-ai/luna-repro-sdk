# LUNA Repro SDK

[한국어](README.md) · [SDK installation](docs/installation-en.md) · [SDK usage and API reference](docs/usage-en.md) · [Platform handbook](https://lunalab-ai.com/workspace/repro/guide/?lang=EN) · [Browser demo](https://lunalab-ai.com/workspace/repro/demo/?lang=EN)

Collect explicitly selected results from Python, Colab or your own server into LUNA result pages. The SDK does not run research, provision GPUs, call AI, or upload directories. Package: `luna-repro`; import: `luna_repro`; CLI: `luna-repro`. Requires Python 3.10+ with no runtime dependencies.

## Install a fixed release

Inside your project virtual environment:

```bash
python -m pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.2.1/luna_repro-0.2.1-py3-none-any.whl
python -c "import luna_repro; print(luna_repro.__version__)"
```

Expect `0.2.1`. Use `%pip install ...` in a separate Colab installation cell. This uses the repository release, not a PyPI package listing. Download and extract `luna-repro-sdk-0.2.1.zip` for `luna-repro-sdk/examples/`; pip does not install or execute teaching notebooks. The ZIP is also installable with `python -m pip install ./luna-repro-sdk-0.2.1.zip`, but building from ZIP may need network access for build tools. Prefer the wheel for offline installation.

## Complete offline example

This computes a synthetic MAE of `0.5` and saves a new local file. The UUID is a teaching placeholder; no network calls occur.

```python
from pathlib import Path
import uuid
import luna_repro as repro

target = [0.0, 1.0, 2.0]
measured = [value + 0.5 for value in target]
mae = sum(abs(a - b) for a, b in zip(target, measured)) / len(target)
page = repro.page("12345678-1234-5678-1234-567812345678", "First synthetic result",
    evidence={"origin": "synthetic", "execution_status": "completed", "evaluation_status": "completed"})
page.section("metrics", "Error").metrics({"MAE": mae, "samples": len(target)})
page.section("rows", "Inputs and predictions").table(["target", "measured"], list(zip(target, measured)))
destination = Path(".luna-repro") / (str(uuid.uuid4()) + ".json")
print(page.save(destination))
```

`python examples/walkthrough.py` computes two results with MAE/RMSE `0.5 → approximately 0.1` and saves them locally. `toy.py` and the browser demo use a different noisy-signal/moving-average calculation. Do not compare these teaching numbers as research performance. After SDK installation, default calculation and save steps remain offline. The notebook installation cell may use the network when SDK 0.2.1 is absent.

## Explicit publication

Obtain your actual permitted project UUID and project connection key from **Connect results** in LUNA. Run the following separately after reviewing the selected content. It defaults to no publication.

```python
import getpass
import os
import uuid

PUBLISH = False
if PUBLISH:
    project_id = str(uuid.UUID(input("Actual project UUID: ").strip()))
    if project_id == "12345678-1234-5678-1234-567812345678":
        raise ValueError("Use your actual permitted project UUID")
    os.environ["LUNA_REPRO_ENDPOINT"] = "https://lunalab-ai.com"
    os.environ["LUNA_REPRO_TOKEN"] = getpass.getpass("Project connection key: ")
    published_page = repro.page(project_id, "First synthetic result", evidence=page.evidence)
    published_page.section("metrics", "Error").metrics({"MAE": mae, "samples": len(target)})
    receipt = published_page.publish()
    print(receipt.get("url") if receipt["status"] == "published" else receipt["message"])
```

Only `status="published"` plus its URL confirms receipt by the platform. `pending` means the local outbox preserves the result but publication is incomplete. Keep keys out of source, saved output, command arguments and URLs. Protect outbox files as private research content.

```bash
python -m luna_repro publish selected-result.json
python -m luna_repro sync --outbox .luna-repro/outbox
```

The CLI reads `LUNA_REPRO_ENDPOINT` and `LUNA_REPRO_TOKEN` from the environment. There is no automatic infinite retry or Trash restoration. For `result_trashed`, restore the result in the platform before an explicit retry. For `authorization_required`, check current access/key expiration; for `storage_quota`, check storage policy; for `rate_limited`, respect `retry_after` before retrying manually.

## Code identity and boundaries

Automatic source metadata identifies the registration call, not the original calculation. Explicit `repro.source.file/function/registration/notebook` helpers require a real `root`. `snapshot=False` is the default; `snapshot=True` includes selected code only. Colab `metadata.id` and Jupyter `id` are distinct. A composed link or locally matched commit does not verify external access, historical execution identity or independent reproduction.

Limits: 8 MiB per image, 16 MiB JSON bundle, 2,000 rows/100 columns per table. Selected source files: 1 MiB; preserved code: 32 KiB/1,000 lines per reference and 256 KiB per page including inherited copies. Try `walkthrough.py --include-source` to preserve selected teaching functions. The notebook defaults to `INCLUDE_SOURCE=False`; configure its real saved file and cell identity before enabling it.

SDK `0.2.1` uses `luna.repro.page.v1` and optional `luna.repro.source.v1`. SDK and platform versions are independent. The server rechecks current project permissions and its own limits. Report composition, Notion delivery and AI review are platform features, not automatic SDK execution.

## Development and release checks

From a Git checkout, use the following commands. Development tests/scripts are intentionally absent from the minimal installer ZIP.

```bash
python -m unittest discover -s tests -v
python scripts/audit_public.py
python scripts/build_release.py --output dist
```

The build uses project-local `setuptools==80.9.0` and `wheel==0.45.1`; no paid workflow is required. Verify downloaded bytes against `SHA256SUMS`. Hashes establish file identity, not an independent signature or research validation. The separate guide ZIP includes manuals and practice files, not an SDK installer. Read LICENSE for the MIT scope and the separate rights of referenced external materials.
