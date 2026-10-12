"""Export selected existing Pasa results. No inference, training or remote reads.

By default only the recorded manifest, camera checks, optional evaluation CSV
and view 003 renders are selected. Explicit options can include bounded view
pairs, training-view diagnostics and a selected notebook source cell. No source
tree, dataset, model checkpoint or complete manifest is uploaded.
"""

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import uuid

import luna_repro as repro


def _selected_file(root, relative, limit, *, required=False):
    root = Path(root).resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Pasa selected file leaves the chosen run directory.")
    if not candidate.is_file():
        if required:
            raise ValueError("Select an existing Pasa output folder with run_manifest.json.")
        return None
    if candidate.stat().st_size > limit:
        raise ValueError("Selected Pasa output exceeds its size limit.")
    with candidate.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Selected Pasa output exceeds its size limit.")
    return data


def _components(values, name):
    if not isinstance(values, list) or len(values) > 40:
        raise ValueError("Pasa %s must be a list with at most 40 entries." % name)
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,149}", value) or value in {".", ".."}:
            raise ValueError("Pasa method/case names must be single safe path components.")
    return values


def build_page(run_dir, *, project, endpoint=None, token=None, notebook_url=None, repository_url=None, commit=None, notebook_sha256=None, gt_available=None, page_id=None, outbox=None, selected_views=None, include_diagnostics=False, include_training_preview=False, notebook_path=None):
    """Import recorded evidence. gt_available=True is an explicit caller assertion.

    A nonempty comparison CSV plus gt_available=True records an imported completed
    evaluation. Neither that declaration nor import is independent verification.
    """
    raw_manifest = _selected_file(run_dir, "run_manifest.json", 1024 * 1024, required=True)
    manifest = json.loads(raw_manifest)
    if not isinstance(manifest, dict):
        raise ValueError("Pasa manifest must be an object.")
    parameters = manifest.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("Pasa manifest parameters must be an object.")
    identity = hashlib.sha256(raw_manifest).hexdigest()
    namespace = uuid.UUID(str(project))
    source = {"file": "VGGT_Gaussian_Surfels_Colab.ipynb"}
    views = ["003"] if selected_views is None else list(selected_views)
    if not views or len(views) > 8 or len(set(views)) != len(views) or any(not isinstance(v, str) or not re.fullmatch(r"[0-9]{3}", v) for v in views):
        raise ValueError("Select one to eight unique three-digit Pasa view IDs.")
    if type(include_diagnostics) is not bool or type(include_training_preview) is not bool:
        raise ValueError("Pasa diagnostic options must be explicit booleans.")
    for key, value in (("execution_url", notebook_url), ("repository_url", repository_url), ("commit", commit), ("snapshot_sha256", notebook_sha256)):
        if value:
            source[key] = value
    result = repro.page(project, "Pasa · " + str(parameters.get("run_name", "recorded run")), description="기존 Pasa 출력에서 가져온 결과입니다. 가져오기는 독립 재현 검증이 아닙니다. Imported Pasa output; not an independent reproduction.", endpoint=endpoint, token=token, page_id=page_id or str(uuid.uuid5(namespace, "pasa-page:" + identity)), run_id=str(uuid.uuid5(namespace, "pasa-run:" + identity)), metadata={"tags": ["Pasa", "imported"]}, evidence={"origin": "imported", "execution_status": "completed" if manifest.get("status") in {"complete", "completed"} else "failed" if manifest.get("status") == "failed" else "unknown", "evaluation_status": "not_run"}, source=source, outbox=outbox)

    def cell(cell_id):
        if notebook_path:
            notebook = Path(notebook_path).resolve()
            # This is a reviewed preparation notebook, not proof of which bytes
            # ran historically. Only the explicitly selected cell is preserved.
            return repro.source.notebook(notebook, cell_id, root=notebook.parent,
                provider="colab" if notebook_url and "colab.research.google.com/" in notebook_url else "jupyter",
                notebook_url=notebook_url, snapshot=True, role="reference")
        ref = {**source, "cell_id": cell_id}
        if notebook_url:
            ref["url"] = notebook_url.split("#", 1)[0] + "#scrollTo=" + cell_id
        return ref

    names = _components(parameters.get("names", []), "names")
    methods = _components(parameters.get("methods", ["surfels"]), "methods")
    if len(names) * len(methods) * (len(views) + int(include_diagnostics) + int(include_training_preview)) > 96:
        raise ValueError("Select a smaller Pasa run; at most 96 method/case previews fit one page.")
    status = result.section("status", "실행 범위와 검증 상태 / Recorded scope", source=cell("cell-04"))
    status.table(["항목 / Item", "값 / Value"], [["선택 케이스 수 / Selected cases", len(names)], ["반복 수 / Iterations", parameters.get("iterations")], ["기록된 pipeline status", manifest.get("status", "unknown")], ["입력 SHA256", parameters.get("input_sha256")], ["구현 SHA256", parameters.get("implementation_sha256")], ["manifest SHA256", identity]])
    status.text("Pipeline 완료는 정량 성능·독립 재현·연구자 검토 완료를 뜻하지 않습니다. Runtime completion does not imply evaluation or independent verification.")
    if notebook_path:
        status.text("연결한 노트북은 검토 시점의 준비 코드입니다. 과거 실행 당시 코드와 동일하다는 증거는 확인되지 않았습니다. The linked notebook is reviewed preparation code; identity with the historical execution is unconfirmed.")
    if include_diagnostics:
        chosen = [("input_mode", "입력 모드 / Input mode"), ("split", "설정에 기록된 split / Recorded split"), ("precision", "정밀도 / Precision"), ("stride", "Stride"), ("depth_weight", "Depth weight"), ("confidence_quantile", "Confidence quantile"), ("occupancy_resolution", "Occupancy resolution")]
        status.table(["설정 / Setting", "값 / Value"], [[label, parameters.get(key)] for key, label in chosen])
    camera_raw = _selected_file(run_dir, "camera_checks.json", 1024 * 1024)
    if camera_raw:
        checks = json.loads(camera_raw)
        if not isinstance(checks, list) or len(checks) > 100:
            raise ValueError("Invalid Pasa camera checks.")
        rows, failed = [], False
        for check in checks:
            if not isinstance(check, dict):
                raise ValueError("Invalid Pasa camera check row.")
            passed = check.get("camera_consistency_pass")
            label = "통과 / Pass" if passed is True else "미통과 / Fail" if passed is False else "알 수 없음 / Unknown"
            failed = failed or passed is False
            rows.append([check.get("sequence"), check.get("points"), label])
        section = result.section("cameras", "카메라 진단 / Camera diagnostics", source=cell("cell-12")).table(["입력 / Case", "점 수 / Points", "일관성 / Consistency"], rows)
        if failed:
            section.text("카메라 진단 미통과가 있습니다. 이후 렌더가 생성되어도 이 진단은 통과로 바뀌지 않습니다. At least one camera check failed; later output generation does not clear it.")
    for method_index, method in enumerate(methods):
        for index, name in enumerate(names):
            for view in views:
                preview = _selected_file(run_dir, Path(method) / name / "renders" / (view + "_render.png"), 8 * 1024 * 1024)
                if preview:
                    key = "render-%d-%d" % (method_index, index) + ("-" + view if selected_views is not None else "")
                    section = result.section(key, method + " · " + name + (" · " + view if selected_views is not None else ""), source=cell("cell-18"))
                    if selected_views is not None:
                        original = _selected_file(run_dir, Path(method) / name / "renders" / (view + "_input.png"), 8 * 1024 * 1024)
                        if original:
                            section.image(original, "저장된 입력 시점 / Recorded input view · " + view)
                    section.image(preview, "기존 실행의 렌더 / Render from the recorded run · " + view)
            if include_training_preview:
                training = _selected_file(run_dir, Path(method) / name / "training_vis.png", 8 * 1024 * 1024)
                if training:
                    result.section("training-%d-%d" % (method_index, index), name + " · 학습 시각화 / Training visualization", source=cell("cell-14")).image(training, "기존 실행에 저장된 학습 시각화입니다. 독립 평가 결과가 아닙니다. Recorded training visualization, not independent evaluation.")
            if include_diagnostics:
                raw = _selected_file(run_dir, Path(method) / name / "renders" / "diagnostics.json", 512 * 1024)
                if raw:
                    diagnostics = json.loads(raw)
                    if not isinstance(diagnostics, dict) or not isinstance(diagnostics.get("views", []), list) or len(diagnostics.get("views", [])) > 100:
                        raise ValueError("Invalid Pasa render diagnostics.")
                    rows = []
                    for item in diagnostics.get("views", []):
                        if not isinstance(item, dict):
                            raise ValueError("Invalid Pasa diagnostic view.")
                        view = item.get("view")
                        if view not in views:
                            continue
                        row = [view]
                        for key in ("surface_points", "foreground_psnr", "full_image_psnr", "foreground_coverage"):
                            value = item.get(key)
                            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                                raise ValueError("Pasa diagnostic values must be finite numbers.")
                            row.append(value)
                        rows.append(row)
                    if rows:
                        section = result.section("diagnostics-%d-%d" % (method_index, index), name + " · 렌더 진단 / Render diagnostics", source=cell("cell-18"))
                        section.text("기록된 측정 범위 / Recorded scope: " + str(diagnostics.get("scope", "unknown")))
                        section.table(["시점 / View", "Surface points", "Foreground PSNR (dB)", "Full-image PSNR (dB)", "Foreground coverage"], rows)
                        section.text("학습 시점 진단은 별도 평가 데이터 성능이나 GT 기반 3D 평가를 대신하지 않습니다. Training-view diagnostics do not establish held-out or ground-truth 3D performance.")
    evaluation = result.section("evaluation", "정량 평가 / Evaluation", source=cell("cell-16"))
    comparison = _selected_file(run_dir, "evaluation/comparison.csv", 2 * 1024 * 1024)
    rows = list(csv.reader(io.StringIO(comparison.decode("utf-8-sig")))) if comparison else []
    if len(rows) > 1:
        evaluation.table(rows[0], rows[1:])
        evaluation.text("평가 단위·정렬·대상 범위를 확인하세요. CSV 가져오기는 독립 검증이 아닙니다. Check units, alignment and evaluated cases; importing CSV is not independent verification.")
    if gt_available is True and len(rows) > 1:
        result.evidence["evaluation_status"] = "completed"
    else:
        evaluation.text("GT 미지정·미확인 또는 평가 결과 누락: 정량 평가 완료로 표시하지 않습니다. Ground truth is missing/unconfirmed or results are absent; evaluation remains not_run.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--notebook-url")
    parser.add_argument("--notebook-path", help="Preserve only selected source cells from this explicitly chosen notebook")
    parser.add_argument("--views", nargs="+", help="Select view pairs, e.g. 000 001 002 003")
    parser.add_argument("--include-diagnostics", action="store_true", help="Include recorded training-view diagnostics, not held-out evaluation")
    parser.add_argument("--include-training-preview", action="store_true")
    parser.add_argument("--gt-available", action="store_true", help="Assert GT was configured for this recorded evaluation")
    args = parser.parse_args()
    try:
        result = build_page(args.run_dir, project=args.project, notebook_url=args.notebook_url, gt_available=args.gt_available,
            notebook_path=args.notebook_path, selected_views=args.views, include_diagnostics=args.include_diagnostics,
            include_training_preview=args.include_training_preview)
        result.save(args.output)
    except (ValueError, TypeError, OSError, KeyError):
        parser.exit(1, "Pasa export failed. Check selected output files and metadata; no execution was started.\n")
    print("Saved selected Pasa result bundle. No inference/training was started.")


if __name__ == "__main__":
    main()
