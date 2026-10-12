"""Explicit, bounded, single-thread matplotlib display capture; never auto-send."""
import io
import threading
import warnings

from . import adapters
from .selection import Candidate, Selection
from .client import _image_mime

_active = threading.Lock()


class Capture:
    def __init__(self, *, max_figures=10, max_bytes=8 * 1024 * 1024):
        if type(max_figures) is not int or not 1 <= max_figures <= 50:
            raise ValueError("Capture supports 1 to 50 figures.")
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 12 * 1024 * 1024:
            raise ValueError("Capture byte budget must be 1 KiB to 12 MiB.")
        self.max_figures, self.max_bytes = max_figures, max_bytes
        self._images, self._warnings, self._seen = [], {}, set()
        self._total, self._dropped, self._failure = 0, 0, False
        self._entered = False

    def __repr__(self):
        return f"Capture(figures={len(self._images)}, dropped={self._dropped}, failed={self._failure})"

    def _take(self, figure):
        if threading.get_ident() != self._owner:
            return
        try:
            if not adapters._is(figure, "matplotlib.figure", "Figure"):
                return
            width, height = figure.get_size_inches() * figure.dpi
            if width * height > adapters.MAX_IMAGE_PIXELS:
                self._dropped += 1
                return
            output = io.BytesIO()
            figure.savefig(output, format="png")
            raw = output.getvalue()
            _image_mime(raw)
            import hashlib
            digest = hashlib.sha256(raw).hexdigest()
            if digest in self._seen:
                return
            if len(self._images) >= self.max_figures or self._total + len(raw) > self.max_bytes:
                self._dropped += 1
                return
            self._seen.add(digest)
            self._images.append(raw)
            self._total += len(raw)
        except (ValueError, OSError, RuntimeError):
            self._dropped += 1

    def __enter__(self):
        if self._entered or not _active.acquire(blocking=False):
            raise RuntimeError("Use one capture scope at a time; nested/concurrent scopes are unsupported.")
        self._entered = True
        self._owner = threading.get_ident()
        self._restore = []
        try:
            # Explicit capture scope opts into loading matplotlib if installed.
            try:
                import matplotlib.pyplot as plt
            except ImportError:
                plt = None
            if plt is not None:
                original_show, original_close = plt.show, plt.close
                def show(*args, **kwargs):
                    for number in plt.get_fignums():
                        self._take(plt.figure(number))
                    return original_show(*args, **kwargs)
                def close(fig=None):
                    if type(fig) is str and fig == "all":
                        figures = [plt.figure(number) for number in plt.get_fignums()]
                    elif adapters._is(fig, "matplotlib.figure", "Figure"):
                        figures = [fig]
                    elif fig is None:
                        figures = [plt.gcf()] if plt.get_fignums() else []
                    elif type(fig) is int and fig in plt.get_fignums():
                        figures = [plt.figure(fig)]
                    else:
                        figures = []
                    for figure in figures:
                        self._take(figure)
                    return original_close(fig)
                plt.show, plt.close = show, close
                self._restore.extend([(plt, "show", original_show), (plt, "close", original_close)])
            original_warning = warnings.showwarning
            def warning(message, category, filename, lineno, file=None, line=None):
                if threading.get_ident() == self._owner:
                    # Count category only: no raw warning message, filename or log capture.
                    name = category.__name__[:100]
                    if name in self._warnings or len(self._warnings) < 20:
                        self._warnings[name] = self._warnings.get(name, 0) + 1
                return original_warning(message, category, filename, lineno, file, line)
            warnings.showwarning = warning
            self._restore.append((warnings, "showwarning", original_warning))
            return self
        except BaseException:
            self._cleanup()
            raise

    def _cleanup(self):
        for module, name, original in reversed(self._restore):
            setattr(module, name, original)
        self._restore = []
        if self._entered:
            self._entered = False
            _active.release()

    def __exit__(self, exc_type, exc, traceback):
        self._failure = exc_type is not None
        self._cleanup()
        return False

    def select(self, *, project=None, title="Captured results", show=True):
        """Return local captured images and failure/warning counts for explicit review."""
        if self._entered:
            raise RuntimeError("Finish the capture scope before selecting its frozen outputs.")
        candidates = [Candidate(f"figure_{i + 1}", "image_bytes", {"kind": "image_bytes", "bytes": len(raw)}, True,
                                "Captured show/close image / 표시·닫기 시점 그림", raw, title=f"Figure {i + 1}")
                      for i, raw in enumerate(self._images)]
        state = {"captured_figures": len(self._images), "dropped_figures": self._dropped,
                 "warning_count": sum(self._warnings.values()), "scope_failed": self._failure}
        candidates.append(Candidate("capture_status", "metrics", {"kind": "metrics", "items": len(state)}, True,
                                    "Warnings/failures retained / 경고·실패 상태 포함", state, title="Capture status"))
        selection = Selection(candidates, project=project, title=title)
        if show:
            selection.show()
        return selection


def capture(*, max_figures=10, max_bytes=8 * 1024 * 1024):
    return Capture(max_figures=max_figures, max_bytes=max_bytes)
