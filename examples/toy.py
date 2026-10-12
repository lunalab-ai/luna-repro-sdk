"""Deterministic, CPU-only synthetic signal demo with two reusable result pages."""

import argparse
import hashlib
import math
from pathlib import Path
import random
import struct
import zlib

try:
    import luna_repro as repro
except ModuleNotFoundError as error:
    if error.name != 'luna_repro':
        raise
    from sdk import luna_repro as repro  # Repository-hosted interactive demo.

SEED = 20261011


def _png(series):
    """Small standard-library chart; all pixels derive from synthetic inputs."""
    width, height = 640, 240
    pixels = bytearray([250, 251, 253] * width * height)

    def point(x, y, color):
        if 0 <= x < width and 0 <= y < height:
            offset = 3 * (y * width + x)
            pixels[offset:offset + 3] = bytes(color)

    colors = [(30, 90, 170), (180, 90, 20), (15, 140, 110)]
    for values, color in zip(series, colors):
        for index in range(1, len(values)):
            x0, x1 = int((index - 1) * (width - 40) / (len(values) - 1)) + 20, int(index * (width - 40) / (len(values) - 1)) + 20
            y0, y1 = int(height / 2 - values[index - 1] * 65), int(height / 2 - values[index] * 65)
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for step in range(steps + 1):
                x, y = round(x0 + (x1 - x0) * step / steps), round(y0 + (y1 - y0) * step / steps)
                point(x, y, color)
                point(x, y + 1, color)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    scanlines = b"".join(b"\x00" + pixels[row * width * 3:(row + 1) * width * 3] for row in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(scanlines, 9)) + chunk(b"IEND", b"")


def build_pages(project, *, endpoint=None, token=None, outbox=None):
    rng = random.Random(SEED)
    reference = [math.sin(index / 12) for index in range(120)]
    noisy = [value + rng.gauss(0, 0.25) for value in reference]
    smooth = [sum(noisy[max(0, index - 2):index + 3]) / len(noisy[max(0, index - 2):index + 3]) for index in range(len(noisy))]
    pages = []
    for label, values in (("baseline", noisy), ("smoothed", smooth)):
        rmse = math.sqrt(sum((actual - expected) ** 2 for actual, expected in zip(values, reference)) / len(reference))
        page = repro.page(project, "합성 신호 / Synthetic signal · " + label, description="결정적 CPU 합성 예제입니다. Pasa·Teeth3DS+ 연구 성능이 아닙니다. Deterministic CPU toy; not Pasa or Teeth3DS+ performance.", endpoint=endpoint, token=token, metadata={"tags": ["synthetic", "CPU", label]}, evidence={"origin": "synthetic", "execution_status": "completed", "evaluation_status": "completed"}, outbox=outbox)
        page.section("metrics", "실제 계산한 합성 지표 / Computed toy metrics").metrics({"RMSE": rmse, "samples": len(reference), "seed": SEED})
        chart = _png((reference, noisy, values))
        page.section("comparison", "신호 비교 / Signal comparison").image(chart, "파랑: 기준 · 주황: 잡음 · 초록: 선택 방법 / Blue: reference; orange: noisy; green: selected method").text("합성 입력과 이미지 SHA256 / Synthetic chart SHA256: " + hashlib.sha256(chart).hexdigest())
        page.section("samples", "일부 결과 / Selected samples").table(["index", "reference", "prediction"], [[index, reference[index], values[index]] for index in range(10)])
        pages.append(page)
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Project UUID from LUNA")
    parser.add_argument("--output", default=".luna-repro/toy")
    parser.add_argument("--publish", action="store_true", help="Explicitly send via environment endpoint/token")
    args = parser.parse_args()
    for index, page in enumerate(build_pages(args.project)):
        page.save(Path(args.output) / ("toy-%d.json" % (index + 1)))
        if args.publish:
            receipt = page.publish()
            print(receipt.get("url") or receipt["message"])
    print("Two synthetic result bundles saved; no GPU or AI call.")


if __name__ == "__main__":
    main()
