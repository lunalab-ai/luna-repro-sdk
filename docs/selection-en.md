# Result discovery, selection and connection — SDK 0.3.0

The SDK runs inside the Python/Colab process that executes your research code. It finds local candidates and sends only reviewed content to a LUNA project. `select()` itself makes no AI request or network transmission. It does not decide whether an experiment succeeded, inspect models or datasets, or crawl working directories.

## 1. First cell: install and connect the project

This installation URL pins the SDK version. Use `%pip` in Colab. Restart the runtime after upgrading an already imported version. Create projects in the platform first.

```bash
python -m pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.3.0/luna_repro-0.3.0-py3-none-any.whl
```

```python
import luna_repro as repro

CONNECT = False  # Enable only after choosing and reviewing the actual project UUID
project_id = "12345678-1234-5678-1234-567812345678"  # Synthetic local demonstration
if CONNECT:
    if project_id == "12345678-1234-5678-1234-567812345678":
        raise ValueError("Choose your actual permitted project UUID")
    connection = repro.connect(project_id, label="Colab", open_browser=False)
else:
    repro.configure(project_id)  # Prepare local preview without network access
```

Connection displays a confirmation code and browser approval link. Sign in to LUNA, compare the **project, request type and code**, and approve. You can click the link directly from Colab. The SDK waits up to ten minutes and keeps the resulting key in memory. Keys are excluded from its return value, notebook output and selection rules. Reconnect after restarting the runtime. An unexpired in-memory connection to the same project can be reused, but the server still checks current access and key revocation on publication.

`connect(project, *, endpoint="https://lunalab-ai.com", label=None, timeout=600, open_browser=True, force=False)` returns nonsecret `project_id`, `project_title`, `expires_at` and `reused`. `label` is `Python`, `Colab` or `Jupyter`; timeout is 1–600 seconds. Use `open_browser=False` to open the displayed link yourself, or `force=True` to explicitly request new approval. Denial, timeout and interruption do not publish results.

Manual keys remain supported. Pass `getpass.getpass()` to `configure(project, endpoint=..., token=...)`; do not hardcode the key. `configure` changes memory defaults only, with no disk/network I/O. `outbox=` selects the preservation directory. `repro.clear()` forgets only the local credential; revoke the server key separately in platform connection management. HTTPS and development loopback HTTP are supported; redirects cannot forward the key.

## 2. Last cell: individual variables need not be listed

```python
metrics = {"MAE": 0.5, "samples": 3}
comparison = [[0.0, 0.5], [1.0, 1.5], [2.0, 2.5]]
failed_check = {"passed": False, "maximum_error": 0.5}
selected = repro.select(purpose="error comparison")
```

`select()` examines only the calling cell/function's local namespace. A notebook typically uses the runtime's user variables. Inside a function only that function's locals are considered; provide `namespace={"metrics": metrics}` when explicit names are preferable. More than 1,000 names or 100 supported candidates requires a narrower scope. Leading underscores, token/secret/password/credential/key-like sensitive names, arbitrary classes, modules, functions and nested objects are excluded. Ordinary strings are not automatically suggested. Name filters are not comprehensive privacy detection: review the contents of tables and figures too.

`purpose=` ranks candidates using simple matches with names, supported metric keys and safe table column names. It is not semantic AI, accuracy verification or a filter that keeps only favorable results. Nonmatching candidates and failures/warnings remain available. Reasons are displayed and you control the checkboxes. Small supported objects are checked initially, but **nothing is sent before the Send action**.

Known setting/loop scalars such as `i`, `epoch`, `batch_size` and `learning_rate` remain candidates but start unchecked. Result/failure candidates such as `loss`, `accuracy`, `failed` and `epoch_loss` remain recommended. This is a name-based guess; review the final selection.

With optional `ipywidgets`, the notebook workflow is checkboxes → title/description/order/conversion options → **Preview** → **Send reviewed**. Enter conversion options as JSON, such as `{"rows": 100, "index": true}`. Changing any control disables Send until another preview. Without widgets, or in a normal `.py` file, only names and reasons appear in the console; values and keys are not automatically printed. Use the same workflow programmatically:

```python
selected = repro.select(namespace={"metrics": metrics, "comparison": comparison,
                                  "failed_check": failed_check}, show=False)
selected.choose("metrics", "comparison", "failed_check")
selected.option("comparison", title="Targets and predictions", columns=["target", "predicted"])
selected.edit(title="Method comparison", description="Synthetic CPU example", order=["metrics", "failed_check", "comparison"])
html_text = selected.preview("preview.html")
selected.save("selected.json")
```

`preview()` returns standalone HTML and saves it when a path is provided. It uses no external scripts or image servers. HTML and JSON contain the selected research content: keep them private. Candidates can be listed before connecting, but a real or synthetic project UUID is required to preview content or save a bundle.

The first preview converts and freezes the selected values. Later changes to the original DataFrame, figure or variable cannot change the bundle or request ID sent by `selected.publish()`. `.choose()`, `.option()` and `.edit()` invalidate that review and freeze again next time. Start a new `select()` for a new run. Changing the configured project after review blocks publication.

```python
PUBLISH = False
if PUBLISH:
    receipt = selected.publish()
    print(receipt)  # Confirm status=published and the result URL
```

`publish(strict=False, timeout=30)` preserves the bundle in the outbox first. Communication failures return `pending`, `outbox_path` and a safe error code. `strict=True` raises after the same local preservation. The default is `.luna-repro/outbox`; successful receipts and originals are retained. There is no background retry. Retry explicitly with the same Selection or the existing `repro.sync(..., endpoint=..., token=...)`/CLI. Memory-only connection settings do not transfer to a separate CLI Python process.

## 3. Explicit publication when you already know the objects

`repro.publish(fig, df, metrics, title="Method comparison")` **explicitly requests immediate publication**. It does not ask for candidate selection again. It uses the same converters and preserves the bundle locally first. Use `select()` for discovery. Calling `publish()` without objects is an error. Explicit strings become text; explicit bytes must be PNG/JPEG images.

Existing `page = repro.page(project, title)` and `page.section(...).metrics/table/image/figure/text` remain supported. `repro.publish(page)` preserves page/run IDs, evidence, sources and sections while using the current memory connection. A project mismatch is rejected. The Page's own `page.publish()`, `page.save()` and v1 protocol remain available. Use the Page API for incremental blocks and exact execution/evaluation evidence. The simple API never automatically declares research success or completed execution.

## 4. Supported objects and conversion rules

| Object | Default representation and explicit options |
| --- | --- |
| Finite number, small name→number dict | Metrics; bool/nonfinite values produce an explicit two-column table |
| List/tuple rows or one-dimensional sequence | Table; use `columns=[...]`; rectangular rows, at most 100 columns |
| pandas DataFrame/Series | Table including the index by default; `index=False` excludes it; `columns=[...]` selects columns |
| NumPy ndarray | Scalar for 0D; table for 1D/2D; object dtype is rejected |
| matplotlib Figure | PNG of the current canvas, without interpreting the experiment |
| PIL Image and official PNG/JPEG decoder objects | PNG; pixels are read after selection |
| pathlib.Path to PNG/JPEG | Unchecked initially; only that chosen file is read after selection |
| Plotly Figure | Unchecked initially; PNG if a compatible static exporter is installed; no automatic browser/exporter installation |
| torch.Tensor | Unchecked initially; detach→CPU copy→NumPy only with `allow_cpu=True`; review possible GPU work and copying |

The SDK does not install or import scientific packages to discover candidates. It recognizes supported objects already used by the research program. Widgets are optionally loaded when a selection UI is requested. It does not call arbitrary user subclasses, properties or repr to guess types. Unsupported custom objects inside tables are rejected rather than stringified.

Limits are 2,000 rows/100 columns per table, 200,000 elements for a general array, 16 million image canvas pixels, 8 MiB per PNG/JPEG and 16 MiB for the JSON bundle. Large tables are not silently truncated. Explicit `selected.option("table", rows=100)` selects the first rows and records the total and chosen range in an explanatory block. The pandas index counts toward the 100-column limit. Dates use ISO 8601, None/pandas NA/NaT become null, and NaN/±Infinity become labelled strings `NaN`, `+Infinity`, `-Infinity`. Nonfinite metrics are not fabricated as finite numbers.

Arrays are not presumed to be images. Choose `as_image=True` and `layout="HWC"` or `"CHW"`. Non-uint8 arrays also require `value_range=[0,1]` or another explicit display range. Nonfinite and out-of-range values are rejected without silent clipping. Color spaces or clinical display conventions are not inferred.

```python
# image_array is your actual ndarray. Select it explicitly when appropriate.
USE_IMAGE = False
if USE_IMAGE:
    images = repro.select(namespace={"render": image_array}, show=False)
    images.choose("render").option("render", as_image=True, value_range=[0, 1], layout="HWC")
    images.preview("image-preview.html")
```

## 5. Figures closed during execution, warnings and failures

```python
CAPTURE_EXAMPLE = False  # Enable only in an environment with matplotlib
if CAPTURE_EXAMPLE:
    import matplotlib.pyplot as plt
    with repro.capture(max_figures=10, max_bytes=8 * 1024 * 1024) as captured:
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 0])
        plt.close(fig)
    selected_capture = captured.select(title="Figures from the chosen scope", show=False)
    selected_capture.preview("capture-preview.html")
```

Only pyplot `show()`/`close()` inside the scope are captured. Outputs outside the scope, ordinary files, stdout/stderr, arbitrary HTML, Plotly display and already closed historical figures are not recovered. Identical PNGs are deduplicated. Limit/conversion drop counts, warning counts and scope failure status remain selectable results. Warning messages, source paths and exception bodies are not saved. Exceptions propagate and hooks are restored, so catch the exception in your caller if you want to review a failed scope afterward. Concurrent/nested scopes are rejected. Capturing figures from other threads is unsupported. Capture is not a program-wide tracer or an automatic publisher.

## 6. Saved selection rules and explicit automatic sending

```python
selected.save_rule("selection-rule.json")  # Automatic sending is off by default
review_again = repro.select(namespace={"metrics": metrics, "comparison": comparison,
                                     "failed_check": failed_check}, rule="selection-rule.json", show=False)
```

Rules store project UUID, selected names/types/order/titles/descriptions/conversion options only. They do not store result values, credentials, the full namespace or source code. Keep sensitive information out of user-authored titles and descriptions too. A missing candidate or changed type/project stops processing instead of silently substituting another object. Same-type changes in meaning or units cannot be detected automatically; review rules when your experiment changes.

Automatic sending requires **both `auto_publish=True` when saving and `auto=True` at invocation**. One invocation sends one new bundle. It does not automatically retry failures or start a training loop, scheduler or AI job. New values under the same variable names can be sent, so enable this only for reviewed repeated workflows. Stop by using `auto=False` or saving the rule without automatic publication.

After automatic sending, inspect `run_selection.receipt` for the actual `published`/`pending` outcome. Before any send, `receipt` is None.

```python
ENABLE_AUTOMATIC_SEND = False
if ENABLE_AUTOMATIC_SEND:
    selected.save_rule("approved-rule.json", auto_publish=True)
    run_selection = repro.select(namespace={"metrics": metrics, "comparison": comparison,
                                            "failed_check": failed_check}, rule="approved-rule.json", auto=True)
```

## 7. Source, AI and recovery boundaries

In Python files, the simple API records the calling filename/line as a registration location. It does not guarantee the line that computed a value, its execution path or causal provenance. Dynamic execution counters are not invented as real notebook cell IDs. For exact lines/cells, commits or selected source snapshots, use existing `repro.source.file/function/notebook(..., snapshot=True)` and `sources={"metrics": source_ref}`, or Page section sources. Choose computation/definition/registration/reference roles truthfully. An assembled link or commit match does not prove historical execution identity, independent reproduction or external access.

`selected.summary()` returns local names/types/sizes/reasons only. The SDK does not automatically send this summary to AI or create separate AI keys/budgets. After publication, use the platform report AI flow to review selected materials, code inclusion, estimated usage and the draft separately. Platform AI usage and Colab/GPU execution costs are separate from SDK installation and local recommendations.

`pending` does not mean the result vanished. Preserve the outbox original, check access/storage/network, then explicitly retry. For `result_trashed`, restore the original result in the platform before retrying; the SDK never silently restores Trash. Distinguish browser-approval errors from research execution failures. Public issue reports should include the SDK version, safe error code and minimal synthetic example, never keys, research bundles, source material or real project IDs.
