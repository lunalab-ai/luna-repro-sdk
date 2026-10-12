"""Real optional scientific objects; runtime adapters never install dependencies."""
from datetime import date
import io
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

import luna_repro as repro
try:
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    OPTIONAL = True
except ImportError:
    OPTIONAL = False

PROJECT = "12345678-1234-5678-1234-567812345678"


@unittest.skipUnless(OPTIONAL, "Install numpy pandas matplotlib Pillow to verify real scientific objects")
class AdapterTests(unittest.TestCase):
    def setUp(self):
        repro.configure(PROJECT)
        self.addCleanup(repro.clear)
        self.addCleanup(plt.close, "all")

    def blocks(self, value, **options):
        selection = repro.select(value, show=False).choose("result_1")
        selection.option("result_1", **options)
        return selection.bundle()["sections"][0]["blocks"]

    def test_dataframe_missing_nonfinite_dates_and_index(self):
        frame = pd.DataFrame({"score": [float("nan"), float("inf")], "day": [date(2026, 1, 1), None]}, index=["a", "b"])
        blocks = self.blocks(frame)
        self.assertEqual(blocks[0]["columns"], ["index", "score", "day"])
        self.assertEqual(blocks[0]["rows"][0], ["a", "NaN", "2026-01-01"])
        self.assertEqual(blocks[0]["rows"][1], ["b", "+Infinity", None])
        self.assertEqual(self.blocks(frame, index=False)[0]["columns"], ["score", "day"])

    def test_numpy_metrics_and_arrays(self):
        self.assertEqual(self.blocks({"error": np.float64(0.5)})[0]["values"], {"error": 0.5})
        self.assertEqual(self.blocks(np.array([[1, 2], [3, 4]]))[0]["rows"], [[1, 2], [3, 4]])
        with self.assertRaises(ValueError):
            self.blocks(np.array([object()], dtype=object))
        with self.assertRaises(ValueError):
            self.blocks(np.zeros((2, 101)))

    def test_large_tables_require_explicit_subset_and_label_it(self):
        frame = pd.DataFrame({"x": range(2001)})
        with self.assertRaises(ValueError):
            self.blocks(frame)
        blocks = self.blocks(frame, rows=3)
        self.assertEqual(len(blocks[0]["rows"]), 3)
        self.assertIn("first 3 of 2001", blocks[1]["text"])
        with self.assertRaises(ValueError):
            self.blocks([[1] * 101])

    def test_pil_decoder_and_float_image_conversion(self):
        stream = io.BytesIO()
        Image.new("RGB", (5, 4), "white").save(stream, "PNG")
        image = Image.open(io.BytesIO(stream.getvalue()))
        self.assertEqual(self.blocks(image)[0]["kind"], "image")
        values = np.ones((4, 5, 3)) * 0.5
        with self.assertRaises(ValueError):
            self.blocks(values, as_image=True)
        blocks = self.blocks(values, as_image=True, value_range=[0, 1])
        self.assertEqual(blocks[0]["kind"], "image")
        self.assertIn("0 to 1", blocks[1]["text"])
        with self.assertRaises(ValueError):
            self.blocks(values * 5, as_image=True, value_range=[0, 1])

    def test_figure_is_png_and_no_remote_call(self):
        figure, axis = plt.subplots()
        axis.plot([0, 1], [1, 0])
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            bundle = repro.select(figure, show=False).bundle()
        self.assertEqual(bundle["artifacts"][0]["mime"], "image/png")

    def test_capture_closed_figure_warnings_and_propagated_failure(self):
        show, close, warning = plt.show, plt.close, warnings.showwarning
        captured = repro.capture()
        with self.assertRaisesRegex(RuntimeError, "not captured"):
            with captured, warnings.catch_warnings():
                warnings.simplefilter("always")
                figure, axis = plt.subplots()
                axis.plot([1, 2])
                plt.close(figure)
                with patch("sys.stderr", new=io.StringIO()):
                    warnings.warn("private warning not in bundle", UserWarning)
                raise RuntimeError("not captured")
        self.assertIs(plt.show, show)
        self.assertIs(plt.close, close)
        self.assertIs(warnings.showwarning, warning)
        bundle = captured.select(show=False).bundle()
        self.assertEqual(len(bundle["artifacts"]), 1)
        text = str(bundle)
        self.assertNotIn("private warning", text)
        self.assertNotIn("not captured", text)
        self.assertIn("scope_failed", text)
        self.assertIn("True", text)

    def test_capture_limits_nested_scope_and_no_automatic_send(self):
        with patch("luna_repro.selection.Selection.publish", side_effect=AssertionError("send")):
            with repro.capture(max_figures=1) as captured:
                with self.assertRaises(RuntimeError):
                    with repro.capture():
                        pass
                for values in ([1, 2], [2, 1]):
                    figure, axis = plt.subplots()
                    axis.plot(values)
                    plt.close(figure)
            self.assertEqual(len(captured._images), 1)
            self.assertEqual(captured._dropped, 1)

    def test_dataframe_arbitrary_cell_is_not_stringified(self):
        class Private:
            def __repr__(self):
                raise AssertionError("private repr")
        with self.assertRaises(ValueError):
            self.blocks(pd.DataFrame({"x": [Private()]}))


if __name__ == "__main__":
    unittest.main()
