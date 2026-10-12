"""Bounded adapters for explicitly selected objects. No repr, eval or imports on discovery."""
from datetime import date, datetime
import io
import json
import math
from pathlib import Path, PosixPath, WindowsPath
import re
import sys
from types import ModuleType

MAX_ELEMENTS = 200000
MAX_IMAGE_PIXELS = 16000000
SECRET_NAME = re.compile(r"(?i)(?:token|secret|password|passwd|credential|api.?key|private.?key|access.?key|ssh.?key|signing.?key|authorization|bearer|cookie|session.?id|connection.?key|(?:^|_)key(?:$|_))")


def safe_name(name):
    return type(name) is str and 0 < len(name) <= 160 and not name.startswith("_") and not SECRET_NAME.search(name)


def _class(module, name):
    loaded = sys.modules.get(module)
    return vars(loaded).get(name) if type(loaded) is ModuleType else None


def _is(value, module, name):
    cls = _class(module, name)
    return cls is not None and type(value) is cls


def _pil(value):
    cls = type(value)
    base = _class("PIL.Image", "Image")
    module, name = type.__getattribute__(cls, "__module__"), type.__getattribute__(cls, "__name__")
    return (base is not None and type(module) is str and module.startswith("PIL.")
            and _class(module, name) is cls and issubclass(cls, base))


def scalar(value):
    """JSON-safe cell conversion; never call an arbitrary object's representation."""
    if value is None or type(value) in {str, bool, int}:
        if type(value) is str and len(value) > 4000:
            raise ValueError("A selected text cell exceeds 4000 characters.")
        if type(value) is int and abs(value) > 1e308:
            raise ValueError("A selected integer exceeds the supported range.")
        return value
    if type(value) is float:
        return value if math.isfinite(value) else "NaN" if math.isnan(value) else "+Infinity" if value > 0 else "-Infinity"
    if type(value) in {date, datetime}:
        return value.isoformat()
    pandas = sys.modules.get("pandas")
    if type(pandas) is ModuleType:
        if value is vars(pandas).get("NA") or value is vars(pandas).get("NaT"):
            return None
        if _is(value, "pandas._libs.tslibs.timestamps", "Timestamp"):
            return value.isoformat()
    numpy = sys.modules.get("numpy")
    if type(numpy) is ModuleType:
        # Exact registered numpy scalar classes, not subclasses with custom methods.
        types = vars(numpy).get("sctypeDict", {})
        if type(types) is dict and type(value) in set(types.values()):
            item = value.item()
            if type(item) is not type(value):
                return scalar(item)
    raise ValueError("Unsupported cell value; choose plain scalars or explicitly convert it first.")


def _label(value):
    if type(value) is tuple:
        return json.dumps([scalar(part) for part in value], ensure_ascii=False)
    value = scalar(value)
    return str(value) if value is not None else "(unnamed)"


def identify(value):
    """Return supported kind, bounded metadata and recommendation. No conversion/I/O."""
    t = type(value)
    if t in {int, float, bool}:
        return "scalar", {"kind": "scalar"}, True, "Small scalar / 작은 수치"
    if t is dict:
        if 0 < len(value) <= 100 and all(safe_name(k) for k in value):
            try:
                if all(type(scalar(v)) in {int, float, bool} or scalar(v) in {"NaN", "+Infinity", "-Infinity"} for v in value.values()):
                    return "metrics", {"kind": "metrics", "items": len(value)}, True, "Named scalar metrics / 이름 있는 지표"
            except (ValueError, TypeError):
                pass
        return None
    if t in {list, tuple} and 0 < len(value) <= MAX_ELEMENTS:
        first = value[0]
        if type(first) in {list, tuple}:
            cols = len(first)
            return "table", {"kind": "table", "rows": len(value), "columns": cols}, len(value) <= 2000 and 0 < cols <= 100, "Rows of values / 행 목록"
        if all(type(v) in {int, float, bool, str, type(None), date, datetime} for v in value[:100]):
            return "series", {"kind": "series", "rows": len(value)}, len(value) <= 2000, "Value sequence / 값 목록"
        return None
    if t in {Path, PosixPath, WindowsPath} and value.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return "image_file", {"kind": "image_file"}, False, "Selected image file; read only after selection / 선택 후 파일 읽기"
    if _is(value, "pandas.core.frame", "DataFrame"):
        rows, cols = value.shape
        return "dataframe", {"kind": "dataframe", "rows": rows, "columns": cols}, rows <= 2000 and cols < 100, "DataFrame; index included / 인덱스 포함 표"
    if _is(value, "pandas.core.series", "Series"):
        return "pandas_series", {"kind": "pandas_series", "rows": len(value)}, len(value) <= 2000, "Series with index / 인덱스 포함 값"
    if _is(value, "numpy", "ndarray"):
        shape = list(value.shape)
        return "array", {"kind": "array", "shape": shape, "dtype": value.dtype.name, "bytes": value.nbytes}, value.ndim <= 2 and value.size <= 2000, "Array; choose table/image when ambiguous / 배열 표현 선택"
    if _is(value, "matplotlib.figure", "Figure"):
        return "figure", {"kind": "figure"}, True, "Explicit matplotlib Figure / 그림 객체"
    if _pil(value):
        return "pil", {"kind": "pil", "width": value.width, "height": value.height, "mode": value.mode}, value.width * value.height <= MAX_IMAGE_PIXELS, "PIL image / 이미지 객체"
    if _is(value, "plotly.graph_objs._figure", "Figure"):
        return "plotly", {"kind": "plotly"}, False, "Static image export requires an optional exporter / 정적 내보내기 필요"
    if _is(value, "torch", "Tensor"):
        return "tensor", {"kind": "tensor", "shape": list(value.shape), "device": value.device.type, "elements": value.numel()}, False, "Explicit detach/CPU conversion required / CPU 변환 선택 필요"
    try:
        converted = scalar(value)
    except ValueError:
        return None
    if type(converted) in {int, float, bool} or (type(converted) is str and converted in {"NaN", "+Infinity", "-Infinity"}):
        return "scalar", {"kind": "scalar"}, True, "Numeric scalar / 수치"
    return None


def _rows(section, columns, rows, *, total, limit, note=""):
    if type(columns) not in {list, tuple} or not 1 <= len(columns) <= 100:
        raise ValueError("Select 1 to 100 columns.")
    if type(rows) not in {list, tuple} or len(rows) > 2000 or any(type(row) not in {list, tuple} or len(row) != len(columns) for row in rows):
        raise ValueError("Select at most 2000 rectangular rows.")
    converted = [[scalar(value) for value in row] for row in rows]
    section.table([_label(c) for c in columns], converted)
    details = "NaN/Infinity are labelled strings; missing values are null; dates use ISO 8601. / 비정상 수치는 문자열, 결측은 null, 날짜는 ISO 8601입니다."
    if total > limit:
        details += f" Selected first {limit} of {total} rows / 전체 {total}행 중 앞 {limit}행 선택."
    if note:
        details += " " + note
    section.text(details)


def convert(section, value, kind, options=None):
    """Convert only an already selected object to existing v1 blocks."""
    options = dict(options or {})
    unknown = set(options) - {"rows", "columns", "index", "as_image", "value_range", "layout", "allow_cpu", "caption"}
    if unknown:
        raise ValueError("Unsupported conversion option.")
    caption = options.get("caption", "")
    limit = options.get("rows", 2000)
    if type(limit) is not int or not 1 <= limit <= 2000:
        raise ValueError("Select 1 to 2000 rows.")
    if kind == "text":
        return section.text(value)
    if kind == "image_bytes":
        return section.image(value, caption, name="captured.png")
    if kind in {"scalar", "metrics"}:
        values = {"value": value} if kind == "scalar" else value
        safe = {key: scalar(item) for key, item in values.items()}
        if all(type(v) in {int, float} for v in safe.values()):
            return section.metrics(safe)
        return _rows(section, ["metric", "value"], list(safe.items()), total=len(safe), limit=100)
    if kind in {"table", "series", "dataframe", "pandas_series"}:
        total = len(value)
        if total > limit and "rows" not in options:
            raise ValueError("Large table: explicitly choose rows=... before previewing.")
        if kind in {"dataframe", "pandas_series"}:
            frame = value if kind == "dataframe" else value.to_frame()
            if "columns" in options:
                if type(options["columns"]) is not list or not all(type(c) in {str, int} for c in options["columns"]):
                    raise ValueError("Choose explicit column names.")
                frame = frame.loc[:, options["columns"]]
            include_index = options.get("index", True)
            if type(include_index) is not bool:
                raise ValueError("index must be a boolean.")
            columns = list(frame.columns)
            if len(columns) + (1 if include_index else 0) > 100:
                raise ValueError("Select at most 100 columns including the index.")
            chosen = frame.iloc[:limit]
            rows = list(chosen.itertuples(index=False, name=None))
            if include_index:
                columns.insert(0, "index")
                rows = [[_label(index), *row] for index, row in zip(chosen.index, rows)]
        else:
            rows = list(value[:limit]) if kind == "table" else [[v] for v in value[:limit]]
            width = len(rows[0]) if rows else 1
            columns = options.get("columns", ["value"] if kind == "series" else [f"column_{i + 1}" for i in range(width)])
        return _rows(section, columns, rows, total=total, limit=limit)
    if kind == "array":
        if value.dtype.hasobject:
            raise ValueError("Object arrays are not inspected or serialized.")
        if options.get("as_image"):
            return _array_image(section, value, options)
        if value.ndim == 0:
            return convert(section, value.item(), "scalar", options)
        if value.ndim not in {1, 2} or value.size > MAX_ELEMENTS:
            raise ValueError("Select a bounded 1D/2D array or explicitly choose as_image=True.")
        if value.shape[0] > limit and "rows" not in options:
            raise ValueError("Large array: explicitly choose rows=... before previewing.")
        chosen = value[:limit]
        width = value.shape[1] if value.ndim == 2 else 1
        if width > 100:
            raise ValueError("Select an array with at most 100 columns.")
        rows = chosen.tolist() if value.ndim == 2 else [[x] for x in chosen.tolist()]
        return _rows(section, options.get("columns", [f"column_{i + 1}" for i in range(width)]), rows, total=value.shape[0], limit=limit)
    if kind == "tensor":
        if options.get("allow_cpu") is not True:
            raise ValueError("Tensor conversion needs explicit allow_cpu=True (detach and CPU copy).")
        if value.numel() > MAX_ELEMENTS:
            raise ValueError("Select a smaller tensor before conversion.")
        array = value.detach().cpu().numpy()
        return convert(section, array, "array", options)
    if kind == "image_file":
        return section.image(value, caption)
    if kind == "figure":
        width, height = value.get_size_inches() * value.dpi
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError("Select a figure of at most 16 million canvas pixels.")
        output = io.BytesIO()
        value.savefig(output, format="png", bbox_inches=None)
        return section.image(output.getvalue(), caption, name="figure.png")
    if kind == "pil":
        if value.width * value.height > MAX_IMAGE_PIXELS:
            raise ValueError("Select an image of at most 16 million pixels.")
        output = io.BytesIO()
        value.save(output, format="PNG")
        return section.image(output.getvalue(), caption, name="selected.png")
    if kind == "plotly":
        try:
            raw = value.to_image(format="png", width=1000, height=600)
        except Exception:
            raise ValueError("Plotly static export is unavailable. Install a compatible optional exporter or select a PNG/JPEG file; no package is installed automatically.") from None
        return section.image(raw, caption, name="plotly.png")
    raise ValueError("Unsupported selected object.")


def _array_image(section, array, options):
    import numpy as np
    from PIL import Image
    if array.dtype.kind not in "buif":
        raise ValueError("Image arrays require real numeric values.")
    if options.get("layout", "HWC") == "CHW":
        if array.ndim != 3:
            raise ValueError("CHW needs a 3D array.")
        array = np.moveaxis(array, 0, -1)
    elif options.get("layout", "HWC") != "HWC":
        raise ValueError("Image layout must be HWC or CHW.")
    if array.ndim not in {2, 3} or (array.ndim == 3 and array.shape[2] not in {3, 4}) or array.shape[0] * array.shape[1] > MAX_IMAGE_PIXELS:
        raise ValueError("Select a bounded grayscale, RGB or RGBA image.")
    note = ""
    if array.dtype != np.uint8:
        bounds = options.get("value_range")
        if type(bounds) not in {list, tuple} or len(bounds) != 2 or not all(type(x) in {int, float} and math.isfinite(x) for x in bounds) or bounds[1] <= bounds[0]:
            raise ValueError("Non-uint8 images require explicit value_range=(minimum, maximum).")
        if not np.isfinite(array).all() or (array < bounds[0]).any() or (array > bounds[1]).any():
            raise ValueError("Image values are nonfinite or outside the explicitly selected range.")
        array = np.rint((array - bounds[0]) * (255.0 / (bounds[1] - bounds[0]))).astype(np.uint8)
        note = f"Image display range {bounds[0]} to {bounds[1]} mapped to uint8 / 표시 범위를 uint8로 변환했습니다."
    convert(section, Image.fromarray(array), "pil", options)
    if note:
        section.text(note)
