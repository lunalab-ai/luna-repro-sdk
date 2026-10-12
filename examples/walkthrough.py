"""An inspectable, standard-library CPU walkthrough. Offline unless --publish.

The numbers are synthetic teaching data, not research performance. Importing this
file and calling build_pages never access the network or write files. A project
key is read only for the explicit --publish action and is never printed/saved.
"""

import argparse
from datetime import datetime, timezone
import getpass
import math
import os
from pathlib import Path
import struct
import uuid
import zlib

try:
    import luna_repro as repro
except ModuleNotFoundError as error:
    if error.name != "luna_repro":
        raise
    from sdk import luna_repro as repro  # Repository-hosted, read-only preview.

OFFLINE_PROJECT = "12345678-1234-5678-1234-567812345678"


def calculate():
    """Six known targets, a +0.5 offset, and an explicitly chosen correction."""
    reference = [float(index) for index in range(6)]
    measured = [value + 0.5 for value in reference]
    corrected = [value - 0.4 for value in measured]
    return reference, measured, corrected


def summarize(reference, prediction):
    errors = [actual - expected for actual, expected in zip(prediction, reference)]
    return {
        "MAE": sum(abs(error) for error in errors) / len(errors),
        "RMSE": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "samples": len(errors),
    }


def chart_png(reference, prediction):
    """Draw the selected six points as a small RGB PNG without extra packages."""
    width, height = 640, 300
    pixels = bytearray([250, 251, 253] * width * height)

    def point(x, y, color):
        if 0 <= x < width and 0 <= y < height:
            offset = 3 * (y * width + x)
            pixels[offset:offset + 3] = bytes(color)

    def line(x0, y0, x1, y1, color):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(steps + 1):
            x = round(x0 + (x1 - x0) * step / steps)
            y = round(y0 + (y1 - y0) * step / steps)
            point(x, y, color)
            point(x, y + 1, color)

    for y in range(30, height - 20, 40):
        line(30, y, width - 25, y, (220, 225, 232))
    for values, color in ((reference, (35, 80, 170)), (prediction, (210, 95, 25))):
        coords = [(30 + index * 115, round(height - 30 - value * 40))
                  for index, value in enumerate(values)]
        for start, end in zip(coords, coords[1:]):
            line(*start, *end, color)
        for x, y in coords:
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    point(x + dx, y + dy, color)

    def chunk(kind, content):
        return (struct.pack(">I", len(content)) + kind + content
                + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff))

    raw = b"".join(b"\x00" + pixels[row * width * 3:(row + 1) * width * 3]
                   for row in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def build_pages(project=OFFLINE_PROJECT, *, outbox=None, include_source=False):
    """Return two complete Page objects; do not save or publish them."""
    reference, measured, corrected = calculate()
    sources = {}
    if include_source:
        # Explicit option: read only selected definitions from this teaching file.
        for key, function in (("conditions", calculate), ("metrics", summarize),
                              ("plot", chart_png), ("samples", build_pages), ("interpretation", calculate)):
            sources[key] = repro.source.function(function, root=Path(__file__).parent, snapshot=True)
    pages = []
    for label, prediction in (("baseline", measured), ("corrected", corrected)):
        page = repro.page(
            project,
            "따라하기 데모 / Walkthrough demo · " + label,
            description=("6개 합성 값으로 결과 등록을 익히는 CPU 예제입니다. "
                         "Six synthetic values teach result registration; not research performance."),
            metadata={"tags": ["synthetic", "walkthrough", "CPU", label]},
            evidence={"origin": "synthetic", "execution_status": "completed",
                      "evaluation_status": "completed"},
            source=sources.get("conditions", {"file": "walkthrough.py"}),
            outbox=outbox,
        )
        page.section("conditions", "계산 조건 / Conditions", source=sources.get("conditions")).text(
            "reference = [0, 1, 2, 3, 4, 5]; measured = reference + 0.5; "
            "corrected = measured - 0.4. CPU, Python standard library, no random input. "
            "MAE = mean(abs(prediction - reference)); RMSE = sqrt(mean(error ** 2))."
        )
        page.section("metrics", "직접 계산한 지표 / Computed metrics", source=sources.get("metrics")).metrics(
            summarize(reference, prediction)
        )
        page.section("plot", "기준과 결과 / Reference and result", source=sources.get("plot")).image(
            chart_png(reference, prediction),
            "파랑: 기준, 주황: 선택 결과 / Blue: reference; orange: selected result",
            name=label + ".png",
        )
        page.section("samples", "6개 값 확인 / Inspect all six values", source=sources.get("samples")).table(
            ["index", "reference", "prediction", "error"],
            [[index, expected, actual, actual - expected]
             for index, (expected, actual) in enumerate(zip(reference, prediction))],
        )
        page.section("interpretation", "해석과 한계 / Interpretation and limits", source=sources.get("interpretation")).text(
            "baseline의 MAE/RMSE는 0.5, corrected는 약 0.1입니다. "
            "알려진 오프셋을 보정한 교육용 계산이며 새 데이터 일반화·독립 재현 검증이 아닙니다. "
            "Baseline MAE/RMSE = 0.5; corrected is approximately 0.1. "
            "This corrects a known synthetic offset; it does not establish generalization "
            "or independent reproduction."
        )
        pages.append(page)
    return pages


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=OFFLINE_PROJECT,
                        help="Real project UUID for publication; offline example UUID otherwise")
    parser.add_argument("--output", default=".luna-repro/walkthrough",
                        help="Private output parent; a new run subfolder preserves earlier files")
    parser.add_argument("--publish", action="store_true",
                        help="Explicitly publish the two saved pages; may prompt for a hidden key")
    parser.add_argument("--include-source", action="store_true",
                        help="Explicitly preserve selected teaching-code definitions with exact lines")
    args = parser.parse_args(argv)
    try:
        project = str(uuid.UUID(args.project))
    except ValueError:
        parser.error("Use the project UUID shown in Connect results.")
    if args.publish and project == OFFLINE_PROJECT:
        parser.error("Publication needs your real --project UUID, not the offline example UUID.")
    if args.publish:
        if not os.environ.get("LUNA_REPRO_ENDPOINT"):
            parser.error("Set LUNA_REPRO_ENDPOINT to your platform HTTPS address first.")
        if not os.environ.get("LUNA_REPRO_TOKEN"):
            os.environ["LUNA_REPRO_TOKEN"] = getpass.getpass("LUNA project key (hidden): ")

    run_folder = (Path(args.output) /
                  (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]))
    pages = build_pages(project, outbox=run_folder / "outbox", include_source=args.include_source)
    pending = False
    for label, page in zip(("baseline", "corrected"), pages):
        saved = page.save(run_folder / (label + ".json"))
        print("Saved:", saved)
        print(label, page.bundle()["sections"][1]["blocks"][0]["values"])
        if args.publish:
            receipt = page.publish()
            if receipt["status"] == "published":
                print("Published:", receipt["url"], "revision", receipt["revision"])
            else:
                pending = True
                print("Pending:", receipt["code"], receipt["message"])
                print("Preserved:", receipt["outbox_path"])
    if not args.publish:
        print("Offline only. No network, GPU or AI call. Files contain selected synthetic data.")
    return int(pending)


if __name__ == "__main__":
    raise SystemExit(main())
