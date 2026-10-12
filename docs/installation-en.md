# Install SDK 0.3.0 and run your first example

Start with the [new selection guide](https://github.com/lunalab-ai/luna-repro-sdk/blob/v0.3.0/docs/selection-en.md) for browser connection and local candidate discovery. The existing Page API and manual-key workflow below remain supported.

[SDK usage and full API](usage-en.md) · [한국어](installation-ko.md)

Use Python 3.10+. Install name: `luna-repro`; import name: `luna_repro`. Installation, synthetic practice and actual platform publication are separate steps. The SDK does not automatically call paid AI/GPU services. Costs of your research servers, data and platform services remain separate.

## Windows PowerShell

Run in a new practice directory; do not replace an existing environment.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.3.0/luna_repro-0.3.0-py3-none-any.whl
.\.venv\Scripts\python.exe -c "import luna_repro; print(luna_repro.__version__)"
```

## Linux or your own server

```bash
python3 -m venv .venv
.venv/bin/python -m pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.3.0/luna_repro-0.3.0-py3-none-any.whl
.venv/bin/python -c "import luna_repro; print(luna_repro.__version__)"
```

These are installation instructions, not a claim of verification on your server. Install optional libraries required by your research project separately in that environment.

## Google Colab

1. Download [walkthrough.ipynb](https://github.com/lunalab-ai/luna-repro-sdk/blob/v0.3.0/examples/walkthrough.ipynb) and open it in Colab.
2. Run this line in a separate installation cell. Installation requires network access.

```python
%pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.3.0/luna_repro-0.3.0-py3-none-any.whl
```

3. Verify that `import luna_repro; print(luna_repro.__version__)` prints `0.3.0`.
4. Leave `PUBLISH=False` and `INCLUDE_SOURCE=False`, then run calculation/save cells. Expect MAE/RMSE of 0.5 and approximately 0.1, plus JSON paths. Download results using Colab's file panel; runtime files can disappear when the session ends.
5. Actual publication requires your real project UUID, hidden connection-key input and an explicit choice. Do not publish the practice UUID. Check `published` before treating transmission as complete.

## Example ZIP, offline installation and hashes

Extract the release's `luna-repro-sdk-0.3.0.zip` to find `luna-repro-sdk/examples/`. Run its `walkthrough.py` with the Python environment where the SDK is installed. Defaults create a new local result directory without network access and preserve prior results. `--publish` is a separate choice.

After downloading the wheel, install without contacting a package index:

```bash
python -m pip install --no-index --no-deps ./luna_repro-0.3.0-py3-none-any.whl
```

ZIP/sdist installation requires the pinned build tools. Use a wheel if those tools are unavailable offline. The wheel contains the SDK; the example ZIP contains installable source and examples; the guide ZIP contains bilingual documentation and examples. Compare each asset with `SHA256SUMS` using PowerShell `Get-FileHash FILE -Algorithm SHA256` or `sha256sum FILE`. Same-release checksums establish transport/file identity, not an independent signature.

## Troubleshooting and version boundaries

- `ModuleNotFoundError`: ensure the Python running the example is the one used for installation.
- Installation URL returns 404: check that the specified release asset has been published. Do not substitute another similarly named package.
- `pending`: preserve the outbox, check the endpoint/current project access/key, then retry explicitly.
- Colab cell links require the actual saved notebook and its `metadata.id`; a filename alone cannot establish an exact cell URL.
- SDK 0.3.0 does not mean platform 0.3.0. The result protocol is `luna.repro.page.v1`, with optional `luna.repro.source.v1`. The server validates current permissions and limits.

For development in a Git checkout, install with `python -m pip install -e .` and run `python -m unittest discover -s tests -v`. Keep README, examples and guides on the same release tag.
