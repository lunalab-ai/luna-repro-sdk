# SDK usage and API reference

[Installation](installation-en.md) · [Platform handbook](https://lunalab-ai.com/workspace/repro/guide/?lang=EN)

SDK 0.2.1 offline practice and explicit result publication. The platform handbook remains the canonical source for report, Notion, AI and permission workflows. Example paths refer to the extracted SDK practice archive. UUIDs are synthetic teaching identifiers.

## 1. The smallest complete Python example

After installing the SDK, run this cell unchanged. It needs no external file, pandas or matplotlib and uses an example UUID for **offline saving only**.

```python
from pathlib import Path
import math
import luna_repro as repro

project_id = "12345678-1234-5678-1234-567812345678"  # Offline practice only
reference = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
prediction = [value + 0.5 for value in reference]
errors = [actual - expected for actual, expected in zip(prediction, reference)]
metrics = {
    "MAE": sum(abs(error) for error in errors) / len(errors),
    "RMSE": math.sqrt(sum(error ** 2 for error in errors) / len(errors)),
    "samples": len(reference),
}
rows = [[i, target, actual] for i, (target, actual)
        in enumerate(zip(reference, prediction))]

page = repro.page(
    project_id,
    "My first synthetic result",
    description="Practice result registration using six synthetic values.",
    metadata={"tags": ["synthetic", "practice"]},
    evidence={"origin": "synthetic", "execution_status": "completed",
              "evaluation_status": "completed"},
)
page.section("conditions", "Conditions").text("Added 0.5 to each reference value.")
page.section("quality", "Quantitative results").metrics(metrics).table(
    ["index", "reference", "prediction"], rows
)
output = Path(".luna-repro") / ("practice-" + page.page_id + ".json")
page.save(output)
print(metrics)  # MAE=0.5, RMSE=0.5, samples=6
print("Saved locally:", output)
```

To publish, replace `project_id` with your actual UUID and rerun page construction. The next connection cell sends to the platform when you explicitly execute it.

```python
import getpass
import os

if page.project_id == "12345678-1234-5678-1234-567812345678":
    raise ValueError("Rebuild the Page using your real project UUID first.")
os.environ["LUNA_REPRO_ENDPOINT"] = "https://lunalab-ai.com"
os.environ["LUNA_REPRO_TOKEN"] = getpass.getpass("LUNA connection key: ")

receipt = page.publish()
if receipt["status"] == "published":
    print("Published:", receipt["url"], "revision:", receipt["revision"])
else:
    print("Pending locally:", receipt["code"], receipt["message"])
    print("Preserved:", receipt.get("outbox_path"))
```

## 2. Add a final cell to your existing research code

First run your research code to produce the selected variables and files. Configure the connection once as described above. This is an **integration example** for code that already defines `project_id`, `metrics`, `comparison_df` and `figure`. Remove lines for objects you do not have or do not need.

```python
import luna_repro as repro

page = repro.page(project_id, "My experiment results")
page.section("quality", "Evaluation").metrics(metrics)
page.section("comparison", "Method comparison").table(comparison_df)
page.section("render", "Visual result").figure(figure, "Selected result figure")
receipt = page.publish()
print(receipt["status"], receipt.get("url") or receipt["message"])
```

This minimal integration does not assert execution status and starts with `imported / unknown / not_run`. If you are recording this actual execution and have performed evaluation, declare that explicitly.

```python
page = repro.page(project_id, "Results from this execution", evidence={
    "origin": "executed",
    "execution_status": "completed",
    "evaluation_status": "completed",
})
```

Keep `evaluation_status="not_run"` when evaluation was not performed. Use `origin="imported"` for previously generated outputs. A rendered image without ground truth does not establish completed quantitative evaluation.

The final cell cannot reconstruct figures you discarded, lost variables, unsaved output or computation locations. Convert large tensors to the specific numbers you need and select image paths explicitly. The SDK does not collect all global variables, directories or the whole notebook.

## 3. Accumulate results across cells and preserve intermediate versions

Create a Page once, then add to the same object from later cells. This complete independent example also runs offline.

```python
import luna_repro as repro

project_id = "12345678-1234-5678-1234-567812345678"  # Replace before publication
page = repro.page(project_id, "Staged synthetic experiment", evidence={
    "origin": "synthetic", "execution_status": "unknown",
    "evaluation_status": "not_run",
})
page.section("setup", "Setup").text("Reference [1, 2, 3], prediction [1.2, 1.8, 3.1]")
page.save(".luna-repro/incremental-example-partial.json")

reference = [1.0, 2.0, 3.0]
prediction = [1.2, 1.8, 3.1]
mae = sum(abs(a - b) for a, b in zip(reference, prediction)) / len(reference)
page.section("quality", "Evaluation").metrics({"MAE": mae})
page.evidence.update(execution_status="completed", evaluation_status="completed")
page.save(".luna-repro/incremental-example-complete.json")
```

With a real project and connection configured, call `page.publish()` at intermediate and final points to preserve new versions of the same page. A file created only by `save()` is not a platform version.

**Reusing a section key appends blocks; it does not replace content.** Running `page.section("quality").metrics(...)` twice creates two metric blocks. Use a new Page for a new experiment or a new explicit section key. If rerunning cells accidentally duplicates blocks, review the needed data and rebuild from the Page-construction cell. The SDK never silently deletes earlier blocks.

To record a new execution under the same page in a new Python session, pass the preserved `page_id` and use a new `run_id`. A new object starts with empty sections; reconstruct everything you want in the new version. Earlier versions remain preserved but are not automatically copied into the object.

```python
import uuid
# saved_page_id is the page_id from an earlier successful receipt.
next_run = repro.page(project_id, "Follow-up execution", page_id=saved_page_id,
                     run_id=str(uuid.uuid4()))
next_run.section("notes", "Scope of this run").text("Results selected for this execution.")
```

## 4. Block syntax and practical examples

The following snippets are calls made after constructing a Page. Every block method returns the same Section, so you can chain `.text(...).metrics(...).table(...)`.

### 11.1 Text

```python
page.section("notes", "Explanation", description="Conditions readers need first").text(
    "Used six inputs.\nThese values are synthetic."
)
```

Text is plain text, not executable HTML or arbitrary Markdown chart rendering. Line breaks are preserved. Include units, inputs, preprocessing, evaluation scope and failure conditions to make the numbers interpretable.

### 11.2 Metrics

```python
page.section("quality", "Quantitative evaluation").metrics({
    "MAE (mm)": 0.25,
    "samples": 24,
    "inference_seconds": 1.8,
})
```

Use names that expose units. Values must be finite numbers; strings such as `"0.25"`, booleans, NaN and Infinity are rejected. In your research code, convert a selected tensor scalar with a suitable expression such as `float(value.item())`. Do not relabel a partially measured inference duration as whole-pipeline time.

### 11.3 Tables and pandas

```python
page.section("table", "Per-case results").table(
    ["case", "score", "passed", "comment"],
    [["A", 0.25, True, "checked"], ["B", None, False, "not evaluated"]],
)
```

Every row must have the same number of cells as columns. Supported cells are numbers, strings, booleans and None. Do not insert a list, dictionary or tensor object directly into a cell.

pandas is an optional dependency only when your research already uses it. `table(df)` does not automatically include the index. Apply this example to an existing `df`.

```python
import pandas as pd  # Needed only in research environments using pandas
selected = df[["case", "score"]].copy()
selected = selected.astype(object).where(pd.notna(selected), None)
page.section("comparison", "Comparison table").table(selected)
# Use selected.reset_index() if the index itself is meaningful.
```

Do not turn missing metrics into zero as if they were measured. Preserve None or explain the omission. Screen previews and clipboard copies show only the first 100 rows and 20 columns. Download **AI review context** to inspect the complete table as JSON.

### 11.4 PNG and JPEG images

```python
from pathlib import Path
image_path = Path("selected_render.png")  # An existing, explicitly selected image
page.section("render", "Front render").image(image_path, "Reconstruction viewed from the front")
```

You can also provide PNG/JPEG bytes from memory.

```python
# image_bytes contains PNG or JPEG bytes produced by your code.
page.section("preview", "Preview").image(image_bytes, "Selected result", name="preview.png")
```

Do not pass a directory, SVG, HTML, PDF, video or 3 D model file to `image()`. If an original contains personal or sensitive information, select an appropriately reviewed/redacted image first. The SDK does not anonymize images automatically.

### 11.5 matplotlib figures

```python
import matplotlib.pyplot as plt  # Needed only when using matplotlib
fig, ax = plt.subplots()
ax.plot([0, 1, 2], [0.5, 1.5, 2.5], marker="o")
ax.set(xlabel="sample", ylabel="value", title="Synthetic values")
page.section("plot", "Synthetic chart").figure(fig, "Three synthetic values")
plt.close(fig)
```

`figure(fig)` and its alias `chart(fig)` export the supplied figure as PNG. After registration into the Page object, closing the figure does not remove the selected image bytes from that object. Interactive Plotly/HTML is not directly supported. Export PNG/JPEG from those tools and explicitly select the file.

## 5. Add precise code, notebook-cell and execution links

Declare provenance using `source`. A new section inherits a copy of the Page source unless given a section-specific source. Changing the Page source later does not retroactively change existing sections.

The registration call and actual computation can occur at different locations. Without an explicit source, the SDK records the registering filename and line where available. It does not infer notebook cells or Git commits.

This example reads the current commit from an actual Git checkout. Replace the repository URL, relative path and lines with your real computation. Uncommitted changes are not contained in that commit; explain dirty changes separately and preserve any needed source snapshot.

```python
import subprocess

commit = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], text=True
).strip()
repository_url = "https://github.com/ORG/REPO"  # Replace with the real repository
source = {
    "repository_url": repository_url,
    "commit": commit,
    "file": "src/inference.py",  # Actual repository-relative computation path
    "line_start": 40,
    "line_end": 63,
    "url": repository_url + "/blob/" + commit + "/src/inference.py#L40-L63",
}
page.section("quality", "Evaluation", source=source)
```

`commit` cannot contain explanatory placeholders such as `main`, `latest` or `EXACT-COMMIT-SHA`. It accepts an actual 40- or 64-character lowercase hexadecimal commit. If unknown, omit the field and explain the missing evidence. Never substitute a recently inspected repository commit for the code used in a past execution.

For a notebook, replace `NOTEBOOK-ID` and `REAL-CELL-ID` with actual values.

```python
notebook_url = "https://colab.research.google.com/drive/NOTEBOOK-ID"
page.section("render", "Reconstruction", source={
    "file": "experiment.ipynb",
    "cell_id": "REAL-CELL-ID",
    "url": notebook_url + "#scrollTo=REAL-CELL-ID",
    "execution_url": notebook_url,
})
```

Setting `cell_id` alone does not produce a clickable cell address. Supply the real cell link in `url`. Verify the saved notebook's cell ID/link; preserve a separate snapshot hash when its content can change. A human label such as cell 18 is not necessarily the actual cell ID.

| source field | Meaning and constraints |
| --- | --- |
| url | HTTPS link to the actual computation or cell |
| repository_url | HTTPS repository link |
| execution_url | Environment the reader can open; does not execute automatically |
| commit | Actual 40/64-character lowercase hexadecimal commit |
| file | Repository-relative path, `/` separators; no absolute path or `..` |
| line_start, line_end | Integers from 1 through 10,000,000; end cannot precede start |
| cell_id | Actual notebook cell identifier, up to 160 characters |
| snapshot_sha 256 | Actual 64-character SHA256 of the selected source snapshot |

URLs must not contain credentials or query strings. Use a permanent address without sharing-query parameters such as `?usp=...`. Use HTTPS on a public hostname; internal IPs, localhost and `.local` are not supported source URLs. Registering a link never automatically grants access to the external resource.

## 6. Offline storage, recovery and key rotation

### 18.1 Saving is separate from sending

`page.save("result.json")` only writes a file. `page.publish()` first writes selected content atomically into the outbox, then attempts transmission. Missing endpoint/key or transport failure usually returns `pending` and a preserved path. Invalid tables, source references or checksums may be rejected before saving.

Outbox and JSON files contain selected research content and images. Treat them as private research data and keep them out of Git. The SDK does not store the token/endpoint in result bundles, but it is not a universal detector of every secret that might be selected. Review what you send.

### 18.2 Retry the same request

After fixing the connection, explicitly run this in the configured Python session.

```python
import luna_repro as repro
outcomes = repro.sync(".luna-repro/outbox")
for receipt in outcomes:
    print(receipt["status"], receipt.get("url") or receipt["code"])
```

The walkthrough uses a per-run outbox, so pass the printed `.../NEW-RUN-DIRECTORY/outbox` path. In its notebook use `repro.sync(run_folder / "outbox")`. A wrong directory may return an empty list; check the actual saved location.

The CLI also works. It reads the token from the session environment and does not accept it as a command argument.

```bash
python -m luna_repro sync --outbox .luna-repro/outbox
python -m luna_repro publish selected-result.json
```

`sync` retries outbox JSON files without successful receipts. `publish file.json` sends that file directly and returns CLI success/failure; it does not independently create an outbox receipt. There is no infinite retry or automatic waiting. Successful originals and receipts are retained.

Use `page.publish(strict=True)` when a pipeline must treat transmission failure as an exception. Errors are sanitized to avoid displaying tokens or raw remote response bodies. HTTP redirects are refused; configure the final HTTPS endpoint.

### 18.3 Expired, lost or replaced keys

Issue a new key → update the runtime secret → confirm actual result intake → revoke the old key. You do not need to rebuild saved result JSON for a new key. Distinguish expired, revoked and project-access-unavailable states. You can revoke your own key even after losing project access. Revocation prevents later API use while preserving previously registered results.

## 7. Apply the adapter to existing Pasa outputs

The adapter imports selected files from an existing Pasa output directory; it does not run new inference. It does not automatically download or modify the original notebook, models or data.

1. Run the existing `VGGT_Gaussian_Surfels_Colab.ipynb` in your own environment and identify the real output directory.
2. Install the SDK and place the downloaded `pasa_adapter.py` somewhere importable.
3. Set `RUN_DIR` to that existing directory. It must contain `run_manifest.json`.
4. Prepare the project UUID and connection.
5. First save local JSON and inspect what was selected.
6. Call `publish()` explicitly only when ready.

```python
from pasa_adapter import build_page

RUN_DIR = "/content/my-existing-pasa-run"  # Replace with the actual output directory
project_id = "12345678-1234-5678-1234-567812345678"  # Replace with the real project UUID
page = build_page(RUN_DIR, project=project_id)
page.save(".luna-repro/pasa-selected-result.json")
# Run explicitly after reviewing the connection, project and selected content:
# receipt = page.publish()
# print(receipt["status"], receipt.get("url") or receipt["message"])
```

The adapter selects these files:

| Path | Treatment |
| --- | --- |
| run_manifest.json | Required; records bounded status/conditions and hashes |
| camera_checks.json | Preserves diagnostic rows and failures if present |
| method/case/renders/003_render.png | Selects this image for method/case entries declared in the manifest |
| evaluation/comparison.csv | Imports the comparison table if present |

It does not upload the complete manifest, raw dataset, checkpoint or source tree. It rejects paths/symlinks escaping the chosen directory. It does not invent missing performance, timing or VRAM observations.

Pass `gt_available=True` only when ground truth was actually configured and a valid comparison CSV exists. Otherwise evaluation stays `not_run`. A completed pipeline is not completed scientific verification. Failed camera diagnostics remain visible even if a later render was generated.

Add `notebook_url`, `repository_url`, `commit` and `notebook_sha256` only when actually known. The same project and manifest hash produce the same page/run IDs. A different owner importing identical output into a separate page should explicitly pass a new `page_id=str(uuid.uuid4())` and explain its provenance/import scope. A fresh CUDA execution and independent reproduction require separate evidence.

## 8. Complete API reference

### 20.1 Page

```text
repro.page(project, title, *, description="", endpoint=None, token=None,
           page_id=None, run_id=None, metadata=None, evidence=None,
           source=None, outbox=None)
```

This is parameter-reference notation. The actual convenience wrapper is `page(project, title, **kwargs)` and forwards to `Page`. `project`, `page_id` and `run_id` are UUIDs; omitted page/run IDs are generated. `metadata` supports only `{"tags": [...]}`. You can pass endpoint/token directly, but never hard-code a real key in shared source; use the session environment or hidden input.

| Method | Result and behavior |
| --- | --- |
| section(key, title=None, description="", source=None) | Section; description/source are keyword-only; existing key reuses its append target |
| bundle() | Validated dict copy, including request_id |
| save(path) | Saved Path; no network call |
| publish(endpoint=None, token=None, strict=False, timeout=30) | Keyword-only arguments; published or pending receipt |

### 20.2 Section

| Method | Input |
| --- | --- |
| text(text) | Plain text |
| metrics(values) | Dict of names to finite numbers |
| table(columns, rows=None) | Columns and rows, or a pandas-compatible DataFrame |
| image(path_or_bytes, caption="", name=None) | PNG/JPEG file or bytes; name is keyword-only |
| figure(figure, caption="") | Explicit figure exported as PNG, or an image path |
| chart(figure, caption="") | Alias of figure |

### 20.3 Files and retries

```python
bundle = repro.load_bundle("selected-result.json")
# Returns a dict; it does not reconstruct a Page object.
receipt = repro.publish_bundle(bundle, timeout=30)
outcomes = repro.sync(".luna-repro/outbox", timeout=30)
```

The publication calls above perform real transmission; prepare the files and connection before executing them. `publish_bundle` and `sync` accept `endpoint`, `token` and `timeout` keyword arguments. Omitted connection values come from `LUNA_REPRO_ENDPOINT` and `LUNA_REPRO_TOKEN`. `PublishError` provides `code`, optional `retry_after` and a fixed sanitized message.

Direct HTTP integrations use `POST /api/repro/v1/pages/`, `GET /api/repro/v1/pages/{page_id}/` and `GET /api/repro/v1/pages/{page_id}/versions/{number}/`. These are project-bearer endpoints and reject browser cookies/Origin. Most users should use the SDK. Do not mix the legacy ReproKit event-v1 contract with this result-page schema.

## 9. Size, cost and status limits

| Item | Current SDK/platform limit |
| --- | --- |
| Python | 3.10 or later |
| Page/section title | SDK 300 characters |
| Page/section description | 12,000 characters |
| Text block | SDK 20,000 characters |
| Section key | 1–80 characters; alphanumeric first, then letters/numbers/underscore/hyphen |
| Metrics block | 1–100 entries;160-character names; finite numbers |
| Table | 1–100 columns,0–2,000 rows;160-character headings;4,000-character string cells |
| PNG/JPEG | 8 MiB each; longest side 8192;16 M total pixels; single frame |
| Entire page | 16 MiB JSON including base 64;100 sections/500 blocks/100 unique images |
| Tags | Up to 30,100 characters each |
| Transmission timeout | Default 30 seconds; greater than 0 and at most 120 |

Key lifetime/count, version limits, project storage, rate limits, reports and Notion policies belong to the platform; check its current handbook. Base 64 expands image data, so two 8 MiB images do not necessarily fit into a 16 MiB JSON bundle.

Registration, viewing, report composition and Notion delivery do not themselves start extra AI or GPU work. Server storage/transfer and existing external-service charges are separate. Actual AI consultation and research execution follow their own environment's permissions and budget.

## 10. Troubleshooting, one issue at a time

| Symptom | What to check or do |
| --- | --- |
| ModuleNotFoundError: luna_repro | Install in the current kernel/environment; use Colab `%pip` or the selected Python's `-m pip` |
| ZIP not found | Upload the ZIP to Colab runtime Files; notebook upload alone does not provide it |
| UUID error | Use the project UUID from Connect results, not its name or secret key |
| Empty project list | Check account, membership and enabled access scope with the administrator |
| Cannot redisplay a key | Expected; use the saved secret or issue a replacement |
| pending / connection_required | Check endpoint, key and timeout format; locate the saved JSON and retry explicitly |
| authorization_required /403 | Check project/key match, key expiry/revocation and current account/project access |
| transport_error | Check final HTTPS endpoint, network and server; do not use a redirecting address |
| 413 or request_limit | Reduce selected images/blocks or split the page |
| storage_quota | Review project storage policy and selected size; do not delete older evidence blindly |
| rate_limited /429 | Wait for retry_after if given, then retry explicitly; do not loop automatically |
| NaN/Infinity rejection | Investigate missing/infinite values; omit invalid metrics with an explanation; tables allow None |
| Table row-length error | Match every row's number of cells to columns |
| SVG/HTML image rejection | Export a bounded PNG/JPEG instead |
| Source commit error | Supply an actual lowercase 40/64-character hash or omit the field |
| Source URL error | Remove query/auth/internal addresses; use a permanent public-host HTTPS URL |
| Cell link opens the wrong place | Verify the real cell ID and sharing scope; cell_id alone creates no link |
| Duplicate metric blocks | Repeated a section-append cell; rebuild the Page or use an explicit new key |
| Same experiment became a new page | Reexecuting Page construction generates new identities; use sync for recovery |
| Empty sync result | Check the outbox path and existing successful receipts |
| request_conflict / page_conflict | Check original request identity, page owner and project; do not randomly rewrite JSON IDs |
| version_limit | Preserve the old page, create a new page and explain/link the relationship |
| Teammate cannot open a link | Check login, current project access and original visibility; do not share a key to bypass access |
| Report save fails | Check section count, same-lab scope, original access, body size and concurrent edits |
| Image does not paste into Notion | Use direct Notion delivery through an authorized connection |
| No Notion destination | Check saved integration, management scope, destination sharing and insertion permission |
| Uncertain Notion result | Inspect the destination and reconcile the remote receipt; do not resend blindly |
| AI cannot inspect code | Provide actual accessible source tools/permissions, commit and file; a result link is not full code |

When asking for help, include the page URL, time, SDK version, error code, expected result and actual result. Do not include connection keys, personal information, private research originals, complete environment variables or authentication headers.

## 11. Verify that your first practice is complete

1. The offline example produced MAE/RMSE 0.5 and approximately 0.1.
2. Your actual project UUID and own key received a `published` receipt.
3. You inspected metrics, charts, tables and provenance on both platform pages.
4. You selected sections from different results and saved a report.
5. You checked the visibility of both original results and the report.
6. You can continue review using a section link or downloaded AI context.
7. Next, choose one small table or figure from real research and register it the same way.

This practice teaches result registration and reporting. Scientific reproducibility additionally requires precise code, data, model, environment and evaluation identities, followed by separate execution and review evidence.

## 12. Preserve calculation lines, cells and selected code with SDK 0.2.1

**A filename-only older result contains limited original evidence.** Its fixed revision is not rewritten. Use the helpers below when registering new results to include a precise location and optional selected text. Recreating the web synthetic demo adds a new CPU-computed, source-enriched revision to the same canonical example page ID. Previous content, hashes and report references remain intact, and an identical repeated request does not create another revision. Trashed examples are never automatically restored. The public finished example also offers **Calculation source → View calculation code**, opening the corresponding lines of the actual teaching file.

### 24.1 What is automatic and what must I select?

The default SDK can record the Python call that registers a result. It does not infer which earlier function or cell calculated it. Virtual notebook execution frames may have no file location. Select computation-related locations explicitly with `source.function(...)`, `source.file(...)` or `source.notebook(...)`. The default is `snapshot=False`, which excludes source text. Only an explicit `snapshot=True` includes selected code in the bundle. Helpers do not save bundles, publish results or execute the selected code.

| Displayed evidence | Meaning |
| --- | --- |
| Result registration location | The SDK call site; it can differ from the calculation |
| User-selected computation code | A calculation range supplied by the user, not proof of successful execution |
| Function/class or cell definition | A saved definition; whether it was called is separate evidence |
| Reference code · execution identity unconfirmed | A review copy whose identity with an earlier execution is unconfirmed |
| Selected code text and hash preserved | Selected text and SHA256 stored with the fixed result revision |
| Producer observed file/commit match | Selected local file bytes matched a local Git commit. The server did not independently verify GitHub or execution |
| Link assembled · external access/execution unverified | A navigation address was constructed. External login, response and execution were not verified |

### 24.2 A complete runnable Python-file example

Install SDK 0.2.1, save this code as a new `source_example.py`, and run `python source_example.py`. It uses `__file__`, so it is a file example rather than a cell to paste unchanged into a notebook. It saves the MAE of three synthetic values (0.5), the calculation function's actual lines and its selected text to local JSON. The UUID is for offline practice. No network, GPU or AI call occurs. Every execution uses a new page ID and preserves previous files.

```python
from pathlib import Path
import luna_repro as repro


def calculate():
    reference = [0.0, 1.0, 2.0]
    prediction = [value + 0.5 for value in reference]
    return sum(abs(a - b) for a, b in zip(prediction, reference)) / len(reference)


selected = repro.source.function(
    calculate, root=Path(__file__).resolve().parent, snapshot=True,
)
page = repro.page(
    "12345678-1234-5678-1234-567812345678", "Source selection practice",
    evidence={"origin": "synthetic", "execution_status": "completed",
              "evaluation_status": "completed"},
)
page.section("metric", "Computed MAE", source=selected).metrics({"MAE": calculate()})
saved = page.save(Path(".luna-repro") / (page.page_id + ".json"))
print("Saved locally:", saved)
print("Source:", selected["file"], selected["line_start"], selected["line_end"])
print("Selected code SHA256:", selected["snapshot_sha256"])
```

Inspect `sections[0].source.provenance.snapshot.text` in the JSON: it should contain only the selected function. Remove secrets, private input data or personal information before transmitting code. To publish, follow the [installation guide](installation-en.md) to set your actual project UUID and connection, then explicitly call `publish()`. Open **Code and execution sources → View preserved code** on the published section to reach its lines. The read-only viewer checks the result's current permissions and never runs code.

The downloaded `walkthrough.py` also supports `python walkthrough.py --include-source`, selecting metric, plot and other relevant definitions. This still saves locally by default. Sending to a real project additionally requires `--project` and `--publish`.

### 24.3 Complete helper syntax and defaults

| Call | Defaults and contract |
| --- | --- |
| `repro.source.file(path, *, root, line_start=1, line_end=None, snapshot=False, repository_url=None, role="computation")` | Select an existing range in a `.py` file. `line_end=None` means the final line. The actual range must exist within a file under `root` |
| `repro.source.function(function, *, root, snapshot=False, repository_url=None)` | Select the saved definition of a function/class with an accessible source file. Role is `definition`. For dynamic/virtual cells, select the actual saved notebook cell |
| `repro.source.registration(*, root, snapshot=False, repository_url=None)` | Capture this helper's call site as `registration`; it does not discover computation code |
| `repro.source.notebook(path, cell_id, *, root, provider="jupyter", notebook_url=None, snapshot=False, repository_url=None, role="definition")` | Select one saved `.ipynb` code cell with the actual matching identity. `provider="colab"` is supported. Use `role="reference"` when identity with an earlier execution is uncertain |

`root` is an explicit existing directory boundary. Resolved paths and symlinks outside it are rejected. No directory traversal or upload is performed. One selected file may be at most 1 MiB. Each preserved reference allows 32 KiB and 1,000 lines, with a 256 KiB aggregate across the page and section copies. Inherited page-source copies count too; select small ranges only for relevant sections. The 16 MiB bundle limit and project storage policy also apply.

### 24.4 Exact GitHub line links

Set `root` to the actual repository root and supply your real `repository_url="https://github.com/organization/repository"`. The helper reads local HEAD and the selected file, and builds a commit-pinned URL only when their bytes match. For Python the form is `.../blob/<exact-commit>/<file>#Lstart-Lend`. Modified files, non-Git directories and unknown identity do not receive an automatic pinned URL. An explicit snapshot still preserves the selected text in LUNA. Git remote credentials are never automatically collected. Byte differences, including CRLF/LF, are not claimed as a match.

A GitHub notebook-file URL is not represented as an exact executable notebook-cell link. The saved file, selected cell text and cell identity can be inspected, while execution-environment navigation uses its provider-specific URL. External repository permissions remain separate from sharing a LUNA result.

### 24.5 Select a real Colab or Jupyter cell

Save a notebook copy as an `.ipynb` file accessible to your runtime. Jupyter uses the cell's top-level `id`; Colab uses its `metadata.id`. They may differ. Do not substitute a displayed cell number or execution counter. The following pattern requires your actual saved file and an **existing cell ID**. Replace every file, ID and URL with your own values.

```python
from pathlib import Path
import luna_repro as repro

notebook_path = Path("saved_notebook.ipynb")
selected = repro.source.notebook(
    notebook_path, "ACTUAL-COLAB-CELL-ID",
    root=notebook_path.resolve().parent,
    provider="colab",
    notebook_url="https://colab.research.google.com/drive/ACTUAL-NOTEBOOK-ID",
    snapshot=True,
    role="reference",
)
```

After matching a saved Colab cell, the helper constructs `#scrollTo=<metadata.id>`. `notebook_url` must contain no query or existing fragment. The helper does not use hidden Colab APIs to discover the currently executing cell, and assembled links are not reported as browser-verified. Missing or duplicated cell identities fail. Unsaved edits, another copy or deleted cells can differ from the original execution; preserve a snapshot and state those limits.

In `walkthrough.ipynb`, `INCLUDE_SOURCE` defaults to False. Upload a saved notebook to the runtime, set `SOURCE_NOTEBOOK`, `SOURCE_PROVIDER` and `SOURCE_CELL_ID` to actual values, change the flag to True, then run the compute/save cell. `SOURCE_NOTEBOOK_URL=None` avoids guessing an external execution link. Notebook outputs, attachments and live global variables are excluded from the selected-code snapshot.

### 24.6 Older results, AI and recovery

Old filename/line references remain unchanged and are not portrayed as new snapshots. Each fixed revision opens its own preserved code. Ordinary AI context, evidence downloads and Notion delivery do not automatically include code text. Only the report AI option **Include code text** adds the selected preserved snapshots that current permissions allow. Missing code stays explicitly missing, and arbitrary external URLs are not fetched. Identity with an earlier execution, data consistency, independent reproduction and research success need separate evidence.

For `invalid_source_snapshot`, reconstruct the selection, range and hashes. For `source_snapshot_limit`, select smaller functions/cells. SDK retries for a result in Trash return `result_trashed` and do not restore it automatically. Restore your result in the platform, then explicitly retry its saved outbox. Revoked access or Trash state also blocks old code links through current authorization checks.
