# SDK 사용법 및 API 참조

브라우저 연결·로컬 자동 후보 선택은 [새 간편 사용법](https://github.com/lunalab-ai/luna-repro-sdk/blob/v0.3.0/docs/selection-ko.md)을 먼저 보세요. 아래 기존 Page API와 직접 키 입력도 계속 지원합니다.

[설치](installation-ko.md) · [플랫폼 가이드](https://lunalab-ai.com/workspace/repro/guide/?lang=KO)

SDK 0.3.0의 오프라인 실습과 명시적 결과 등록 안내입니다. 플랫폼 보고서·Notion·AI·권한 관리의 상세 원본은 위 플랫폼 가이드에서 확인하세요. 아래 예제 경로는 SDK 예제 ZIP을 푼 위치를 기준으로 합니다. UUID는 합성 연습용입니다.

## 1. 가장 작은 완전한 Python 예제

SDK 설치 후 아래 셀은 외부 파일·pandas·matplotlib 없이 그대로 실행할 수 있습니다. 연습용 UUID로 **오프라인 저장만** 합니다.

```python
from pathlib import Path
import math
import luna_repro as repro

project_id = "12345678-1234-5678-1234-567812345678"  # 오프라인 연습용
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
    "첫 합성 결과",
    description="6개 합성 값으로 등록 문법을 연습합니다.",
    metadata={"tags": ["synthetic", "practice"]},
    evidence={"origin": "synthetic", "execution_status": "completed",
              "evaluation_status": "completed"},
)
page.section("conditions", "계산 조건").text("기준 값에 0.5를 더했습니다.")
page.section("quality", "정량 결과").metrics(metrics).table(
    ["index", "reference", "prediction"], rows
)
output = Path(".luna-repro") / ("practice-" + page.page_id + ".json")
page.save(output)
print(metrics)  # MAE=0.5, RMSE=0.5, samples=6
print("로컬 저장:", output)
```

실제로 보내려면 첫 줄의 `project_id`를 실제 UUID로 바꾸고 Page 생성부터 다시 실행합니다. 다음 연결 셀은 사용자가 명시적으로 실행할 때 플랫폼 전송을 합니다.

```python
import getpass
import os

if page.project_id == "12345678-1234-5678-1234-567812345678":
    raise ValueError("실제 프로젝트 UUID로 Page를 다시 만들어 주세요.")
os.environ["LUNA_REPRO_ENDPOINT"] = "https://lunalab-ai.com"
os.environ["LUNA_REPRO_TOKEN"] = getpass.getpass("LUNA 연결 키: ")

receipt = page.publish()
if receipt["status"] == "published":
    print("등록 완료:", receipt["url"], "버전:", receipt["revision"])
else:
    print("로컬 대기:", receipt["code"], receipt["message"])
    print("보존 위치:", receipt.get("outbox_path"))
```

## 2. 기존 연구 코드의 마지막 셀에 붙이기

먼저 연구 코드를 실행해 필요한 변수·파일을 만듭니다. 연결 설정은 앞 절처럼 한 번 준비합니다. 아래는 `project_id`, `metrics`, `comparison_df`, `figure`가 이미 존재하는 연구 코드에 붙이는 **통합 예시**입니다. 필요하지 않거나 아직 없는 객체의 줄은 제거합니다.

```python
import luna_repro as repro

page = repro.page(project_id, "내 실험 결과")
page.section("quality", "정량 평가").metrics(metrics)
page.section("comparison", "방법 비교").table(comparison_df)
page.section("render", "시각 결과").figure(figure, "선택한 결과 그림")
receipt = page.publish()
print(receipt["status"], receipt.get("url") or receipt["message"])
```

이 최소 통합 예시는 실행 상태를 자동 단정하지 않으므로 `imported / unknown / not_run`으로 시작합니다. 실제 이번 코드 실행을 기록하고 평가까지 수행했다면 다음처럼 명시합니다.

```python
page = repro.page(project_id, "이번 실행의 결과", evidence={
    "origin": "executed",
    "execution_status": "completed",
    "evaluation_status": "completed",
})
```

평가를 하지 않았다면 `evaluation_status="not_run"`을 유지합니다. 예전 산출물을 불러온 경우에는 `origin="imported"`입니다. GT가 없는 렌더 이미지가 만들어졌다고 정량 평가 완료로 표시하지 않습니다.

마지막 셀은 이미 닫아 버린 그림, 사라진 변수, 저장하지 않은 출력, 계산 위치를 복원하지 못합니다. 큰 Tensor는 필요한 숫자로 변환하고, 이미지는 원하는 경로를 명시합니다. 모든 전역 변수·폴더·노트북을 자동 수집하지 않습니다.

## 3. 실행 중 여러 셀에서 쌓고 중간 버전 남기기

처음에 Page 객체를 만들고 여러 셀에서 같은 객체에 추가합니다. 아래는 오프라인으로도 실행 가능한 독립 예제입니다.

```python
import luna_repro as repro

project_id = "12345678-1234-5678-1234-567812345678"  # 전송 전 실제 UUID로 교체
page = repro.page(project_id, "단계별 합성 실험", evidence={
    "origin": "synthetic", "execution_status": "unknown",
    "evaluation_status": "not_run",
})
page.section("setup", "준비").text("기준 [1, 2, 3], 예측 [1.2, 1.8, 3.1]")
page.save(".luna-repro/incremental-example-partial.json")

reference = [1.0, 2.0, 3.0]
prediction = [1.2, 1.8, 3.1]
mae = sum(abs(a - b) for a, b in zip(reference, prediction)) / len(reference)
page.section("quality", "평가").metrics({"MAE": mae})
page.evidence.update(execution_status="completed", evaluation_status="completed")
page.save(".luna-repro/incremental-example-complete.json")
```

연결을 준비한 실제 프로젝트에서 중간·최종 시점에 `page.publish()`를 각각 실행하면 같은 페이지에 새 결과 버전이 쌓입니다. `save()`만 실행한 파일은 플랫폼 버전이 아닙니다.

**같은 섹션 key는 내용 교체가 아니라 블록 추가입니다.** `page.section("quality").metrics(...)` 셀을 두 번 실행하면 지표 블록도 두 개 생깁니다. 새 실험은 새 Page로 기록하거나 새 명시적 섹션 key를 사용합니다. 셀 재실행으로 중복 블록을 만들었으면 아직 필요한 자료를 확인한 뒤 Page 생성 셀부터 다시 구성합니다. SDK는 기존 블록을 자동 삭제하지 않습니다.

새 Python 세션에서 같은 페이지의 새 실행을 남기려면 보관한 `page_id`를 전달하고 새 `run_id`를 사용합니다. 이때 새 객체의 섹션은 비어 있으므로 최종 버전에 포함할 내용을 모두 다시 구성해야 합니다. 이전 버전은 보존되지만 자동으로 새 객체에 복사되지 않습니다.

```python
import uuid
# saved_page_id는 이전 성공 영수증의 page_id입니다.
next_run = repro.page(project_id, "후속 실행", page_id=saved_page_id,
                     run_id=str(uuid.uuid4()))
next_run.section("notes", "이번 실행 범위").text("이번에 선택해 등록할 결과입니다.")
```

## 4. 블록별 문법과 실무 예시

다음 예시는 Page를 만든 뒤 호출하는 문법입니다. 각 메서드는 같은 Section을 반환하므로 `.text(...).metrics(...).table(...)`처럼 이어 붙일 수 있습니다.

### 11.1 설명

```python
page.section("notes", "설명", description="독자가 먼저 알아야 할 조건").text(
    "입력 6개를 사용했습니다.\n이 값은 합성 예제입니다."
)
```

text는 일반 텍스트입니다. HTML 실행이나 임의 Markdown 차트 렌더링을 제공하지 않습니다. 줄바꿈은 보존됩니다. 단위·입력·전처리·평가 범위·실패 조건을 적어 두면 숫자 해석에 도움이 됩니다.

### 11.2 지표

```python
page.section("quality", "정량 평가").metrics({
    "MAE (mm)": 0.25,
    "samples": 24,
    "inference_seconds": 1.8,
})
```

이름은 단위가 드러나게 정합니다. 유한한 숫자만 허용합니다. 문자열 `"0.25"`, bool, NaN, Infinity는 거절합니다. Tensor 값은 연구 코드에서 `float(value.item())`처럼 필요한 스칼라로 바꾸어 전달합니다. 시간 일부만 측정했다면 전체 파이프라인 시간이라고 표시하지 않습니다.

### 11.3 표와 pandas

```python
page.section("table", "사례별 결과").table(
    ["case", "score", "passed", "comment"],
    [["A", 0.25, True, "확인"], ["B", None, False, "평가 미실시"]],
)
```

행마다 열 개수가 같아야 합니다. 숫자·문자열·bool·None만 들어갈 수 있습니다. 표 안에 리스트·딕셔너리·Tensor 객체를 직접 넣지 않습니다.

pandas는 연구 코드에서 이미 사용할 때만 필요한 선택 의존성입니다. `table(df)`는 index를 자동 포함하지 않습니다. 다음 예시는 기존 `df`가 있을 때 적용합니다.

```python
import pandas as pd  # pandas를 사용하는 연구 환경에서만 필요
selected = df[["case", "score"]].copy()
selected = selected.astype(object).where(pd.notna(selected), None)
page.section("comparison", "비교표").table(selected)
# index 자체가 중요하면 selected.reset_index()를 전달합니다.
```

누락 수치를0으로 바꾸어 평가한 것처럼 보이게 하지 마세요. None 또는 별도 설명으로 남깁니다. 화면 미리보기·복사는 처음100행·20열까지만 보이며 전체 표는 **AI 검토 자료** JSON에서 확인할 수 있습니다.

### 11.4 PNG·JPEG 이미지

```python
from pathlib import Path
image_path = Path("selected_render.png")  # 실제 존재하는 선택 이미지
page.section("render", "정면 렌더").image(image_path, "정면에서 본 복원 결과")
```

메모리의 PNG/JPEG bytes도 가능합니다.

```python
# image_bytes는 연구 코드가 만든 PNG 또는 JPEG bytes입니다.
page.section("preview", "미리보기").image(image_bytes, "선택 결과", name="preview.png")
```

폴더·SVG·HTML·PDF·동영상·3D 모델 파일을 `image()`에 전달하지 않습니다. 원본에 개인정보·민감 정보가 들어 있다면 연구자가 적절한 선택·가림 처리를 마친 이미지만 등록합니다. SDK가 자동 익명화하지 않습니다.

### 11.5 matplotlib 그래프

```python
import matplotlib.pyplot as plt  # matplotlib을 사용하는 연구 환경에서만 필요
fig, ax = plt.subplots()
ax.plot([0, 1, 2], [0.5, 1.5, 2.5], marker="o")
ax.set(xlabel="sample", ylabel="value", title="Synthetic values")
page.section("plot", "합성 그래프").figure(fig, "3개 합성 값")
plt.close(fig)
```

`figure(fig)` 또는 별칭 `chart(fig)`는 넘긴 figure 하나를 PNG로 내보냅니다. 이미지 등록 후 figure를 닫아도 등록 객체에는 선택 이미지가 남습니다. 인터랙티브 Plotly·HTML을 직접 지원하지 않습니다. 그런 도구는 연구 코드에서 PNG/JPEG로 내보낸 파일을 선택하세요.

## 5. 코드·노트북 셀·실행 환경 링크를 정확히 넣기

코드 출처는 `source`에 명시합니다. Page의 출처는 새 섹션에 사본으로 상속되고, 섹션별 출처를 주면 그 섹션이 별도 출처를 가집니다. 상속 후 Page 출처를 수정해도 이미 만든 섹션의 출처는 자동 변경되지 않습니다.

등록 함수 호출 줄과 실제 계산 줄은 다릅니다. 아무것도 지정하지 않으면 SDK는 가능한 경우 등록한 파일명과 줄만 기록합니다. 노트북 셀이나 Git 커밋을 자동 추측하지 않습니다.

아래는 실제 Git 저장소 폴더에서 현재 커밋을 읽는 출처 구성 예시입니다. 프로젝트 저장소 주소와 실제 상대 경로·줄은 본인 코드에 맞춰야 합니다. dirty 상태의 수정분은 commit에 포함되지 않으므로 별도로 설명하고 필요한 소스 스냅샷을 보존합니다.

```python
import subprocess

commit = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], text=True
).strip()
repository_url = "https://github.com/ORG/REPO"  # 실제 저장소 주소로 교체
source = {
    "repository_url": repository_url,
    "commit": commit,
    "file": "src/inference.py",  # 실제 계산 파일의 저장소 상대경로
    "line_start": 40,
    "line_end": 63,
    "url": repository_url + "/blob/" + commit + "/src/inference.py#L40-L63",
}
page.section("quality", "정량 평가", source=source)
```

`commit`에는 `main`, `latest`, `EXACT-COMMIT-SHA` 같은 설명용 문구를 넣을 수 없습니다. 실제 소문자40자리 또는64자리16진수만 허용합니다. 모르면 해당 필드를 생략하고 미확인 상태를 설명합니다. 나중에 검토한 최신 commit을 과거 실행 commit이라고 대신 적지 않습니다.

노트북 예시는 다음과 같습니다. `NOTEBOOK-ID`, `REAL-CELL-ID`는 실제 값으로 교체합니다.

```python
notebook_url = "https://colab.research.google.com/drive/NOTEBOOK-ID"
page.section("render", "복원 결과", source={
    "file": "experiment.ipynb",
    "cell_id": "REAL-CELL-ID",
    "url": notebook_url + "#scrollTo=REAL-CELL-ID",
    "execution_url": notebook_url,
})
```

`cell_id`만 적으면 클릭 가능한 셀 주소가 자동 생성되지 않습니다. 실제 셀 링크를 `url`로 지정합니다. Colab 노트북의 저장된 셀 ID·링크를 확인하고 변경될 수 있는 노트북은 별도 스냅샷 hash도 보존합니다. 셀 번호18과 셀 ID는 반드시 같은 값이 아닙니다.

| source 필드 | 의미·제약 |
| --- | --- |
| url | 해당 계산 코드·셀의 HTTPS 링크 |
| repository_url | HTTPS 저장소 링크 |
| execution_url | 사용자가 열 실행 환경 링크. 자동 실행 아님 |
| commit | 실제40/64자리 소문자16진수 commit |
| file | 저장소 상대경로. `/` 구분, `..`·절대경로 금지 |
| line_start, line_end | 1이상10,000,000이하 정수. 끝이 시작보다 작을 수 없음 |
| cell_id | 실제 노트북 셀 식별자,160자 이하 |
| snapshot_sha256 | 실제 선택 소스 스냅샷의64자리 SHA256 |

URL에는 인증정보·query string을 넣지 않습니다. 공유 URL의 `?usp=...` 등도 제거한 영속 주소를 사용합니다. HTTPS 공개 호스트 이름을 사용하며 내부 IP·localhost·`.local`은 출처 URL로 허용하지 않습니다. 외부 링크를 기록해도 그 자료의 읽기 권한이 자동으로 공유되지는 않습니다.

## 6. 오프라인 저장·실패 복구·키 교체

### 18.1 저장과 전송은 별개입니다

`page.save("result.json")`은 파일만 저장합니다. `page.publish()`는 먼저 선택 결과를 outbox에 원자적으로 저장하고 전송을 시도합니다. endpoint·키가 없거나 네트워크가 실패하면 보통 `pending`과 경로를 반환합니다. 유효하지 않은 표·출처·체크섬 등은 저장 전에 예외로 거절될 수 있습니다.

outbox와 JSON에는 선택한 연구 내용·이미지가 들어 있습니다. 비공개 연구자료로 보관하고 Git에 넣지 않습니다. SDK는 토큰·endpoint를 결과 묶음에 저장하지 않지만 선택한 모든 데이터의 비밀을 자동 탐지하는 도구는 아닙니다. 무엇을 보낼지는 사용자가 확인합니다.

### 18.2 같은 요청 재전송

연결을 바로잡은 같은 Python 세션에서 다음을 명시적으로 실행합니다.

```python
import luna_repro as repro
outcomes = repro.sync(".luna-repro/outbox")
for receipt in outcomes:
    print(receipt["status"], receipt.get("url") or receipt["code"])
```

walkthrough는 실행별 outbox를 사용하므로 출력에 나온 `.../새실행폴더/outbox`를 전달합니다. 노트북에서는 `repro.sync(run_folder / "outbox")`입니다. 폴더가 틀리면 빈 목록이 나올 수 있으므로 저장 경로를 확인하세요.

CLI도 가능합니다. 토큰은 현재 세션 환경에서 읽으며 명령 인수로 받지 않습니다.

```bash
python -m luna_repro sync --outbox .luna-repro/outbox
python -m luna_repro publish selected-result.json
```

`sync`는 성공 영수증이 없는 outbox JSON만 재시도합니다. `publish 파일.json`은 지정 파일을 직접 전송하고 CLI 성공·실패를 반환하며 outbox 영수증을 별도 생성하지 않습니다. SDK는 무한 재시도나 자동 대기를 하지 않습니다. 성공 원본과 영수증도 자동 삭제하지 않습니다.

파이프라인에서 전송 실패를 예외로 처리하려면 `page.publish(strict=True)`를 사용합니다. 오류의 원격 응답 원문·토큰은 표시하지 않도록 처리되어 있습니다. HTTP redirect는 거절하므로 endpoint는 최종 HTTPS 주소여야 합니다.

### 18.3 키 만료·분실·교체

새 키 발급 → 실행 환경의 비밀 설정 교체 → 실제 결과 수신 확인 → 이전 키 해제 순서로 진행합니다. 저장된 결과 JSON을 새 키 때문에 다시 만들 필요는 없습니다. 만료·해제·현재 프로젝트 접근 불가를 구분하고, 접근을 잃은 본인 키도 연결 관리에서 해제할 수 있습니다. 키를 해제하면 이후 API 사용이 막히며 이미 등록된 결과는 보존됩니다.

## 7. Pasa의 기존 출력에 적용하기

이 어댑터는 Pasa 추론을 새로 실행하지 않습니다. 이미 생성된 출력 폴더에서 선택 결과를 가져옵니다. 원래 노트북·모델·데이터를 자동 다운로드하거나 수정하지 않습니다.

1. 기존 `VGGT_Gaussian_Surfels_Colab.ipynb`를 자신의 환경에서 실행하고 실제 출력 폴더를 확인합니다.
2. SDK를 설치하고 다운로드 예제의 `pasa_adapter.py`를 import할 수 있는 폴더에 둡니다.
3. `RUN_DIR`에 실제 기존 출력 폴더를 넣습니다. 폴더에는 `run_manifest.json`이 있어야 합니다.
4. 프로젝트 UUID와 연결을 준비합니다.
5. 먼저 로컬 JSON 저장까지 실행하여 선택 범위를 확인합니다.
6. 필요하면 명시적으로 `publish()`를 실행합니다.

```python
from pasa_adapter import build_page

RUN_DIR = "/content/my-existing-pasa-run"  # 실제 출력 폴더로 교체
project_id = "12345678-1234-5678-1234-567812345678"  # 실제 프로젝트 UUID로 교체
page = build_page(RUN_DIR, project=project_id)
page.save(".luna-repro/pasa-selected-result.json")
# 연결·프로젝트·선택 결과를 확인한 뒤 명시적으로 실행:
# receipt = page.publish()
# print(receipt["status"], receipt.get("url") or receipt["message"])
```

선택하는 파일은 다음과 같습니다.

| 경로 | 처리 |
| --- | --- |
| run_manifest.json | 필수. 제한된 실행 상태·조건과 hash만 기록 |
| camera_checks.json | 있으면 진단 표와 실패 기록 보존 |
| method/case/renders/003_render.png | manifest에 지정된 method/case의 해당 이미지만 선택 |
| evaluation/comparison.csv | 있으면 비교 표를 가져옴 |

전체 manifest·원본 데이터·checkpoint·소스 트리를 업로드하지 않습니다. 선택 폴더 밖으로 나가는 경로·파일 링크를 거절합니다. manifest에 없는 성능·시간·VRAM을 만들어 넣지 않습니다.

GT를 실제 설정하여 평가했고 유효한 비교 CSV가 있는 경우에만 `gt_available=True`를 명시합니다. 그렇지 않으면 평가 상태는 `not_run`입니다. pipeline의 완료 상태는 연구 검증 완료가 아닙니다. 카메라 진단 실패는 이후 렌더가 생성되어도 그대로 남습니다.

정확히 알고 있을 때만 `notebook_url`, `repository_url`, `commit`, `notebook_sha256`을 추가합니다. 같은 프로젝트·manifest hash는 같은 page/run ID를 만듭니다. 다른 소유자가 동일 출력을 자기 페이지로 가져오려면 새 `page_id=str(uuid.uuid4())`를 명시하고 출처·가져오기 범위를 설명합니다. 실제 새 CUDA 실행과 독립 재현 검증은 별도 절차로 확인해야 합니다.

## 8. 전체 API 참조

### 20.1 Page

```text
repro.page(project, title, *, description="", endpoint=None, token=None,
           page_id=None, run_id=None, metadata=None, evidence=None,
           source=None, outbox=None)
```

위 표기는 함수 인자 설명입니다. 실제 래퍼는 `page(project, title, **kwargs)`이고 `Page` 생성자에 전달합니다. `project`, `page_id`, `run_id`는 UUID입니다. page/run ID 생략 시 새로 만듭니다. `metadata={"tags": [...]}` 외 필드는 지원하지 않습니다. `endpoint`·`token`을 객체에 직접 지정할 수도 있지만, 공유 소스에 실제 값을 쓰지 말고 세션 환경·숨김 입력을 사용합니다.

| 메서드 | 반환·주의 |
| --- | --- |
| section(key, title=None, description="", source=None) | Section. description/source는 키워드 인자. 같은 key는 추가 대상 재사용 |
| bundle() | 검증된 dict 사본. request_id 포함 |
| save(path) | 저장 Path. 네트워크 호출 없음 |
| publish(endpoint=None, token=None, strict=False, timeout=30) | 키워드 인자만 사용. 성공 또는 pending 영수증 |

### 20.2 Section

| 메서드 | 입력 |
| --- | --- |
| text(text) | 일반 텍스트 |
| metrics(values) | 이름→유한 숫자 dict |
| table(columns, rows=None) | 열+행 또는 pandas 호환 DataFrame |
| image(path_or_bytes, caption="", name=None) | PNG/JPEG 파일·bytes. name은 키워드 인자 |
| figure(figure, caption="") | 명시 figure의 PNG 내보내기 또는 이미지 경로 |
| chart(figure, caption="") | figure의 별칭 |

### 20.3 파일과 재전송

```python
bundle = repro.load_bundle("selected-result.json")
# dict를 읽습니다. Page 객체를 복원하는 함수는 아닙니다.
receipt = repro.publish_bundle(bundle, timeout=30)
outcomes = repro.sync(".luna-repro/outbox", timeout=30)
```

이 코드는 두 번째 줄부터 실제 전송을 시도하므로 연결과 파일을 준비한 뒤 실행합니다. `publish_bundle`·`sync`에도 `endpoint`, `token`, `timeout` 키워드를 지정할 수 있습니다. 연결 값을 생략하면 `LUNA_REPRO_ENDPOINT`, `LUNA_REPRO_TOKEN`에서 읽습니다. `PublishError`는 `code`, 선택적 `retry_after`와 고정 오류 안내를 갖습니다.

직접 HTTP를 구현할 때는 `POST /api/repro/v1/pages/`, `GET /api/repro/v1/pages/{page_id}/`, `GET /api/repro/v1/pages/{page_id}/versions/{number}/`를 사용합니다. 프로젝트 bearer 전용이며 브라우저 쿠키·Origin을 포함한 요청은 거절합니다. 일반 사용자는 SDK를 권장합니다. 구 ReproKit 이벤트 v1과 이 결과 페이지 스키마를 섞지 않습니다.

## 9. 크기·비용·상태 한도

| 항목 | 현재 SDK·플랫폼 한도 |
| --- | --- |
| Python | 3.10 이상 |
| 페이지·섹션 제목 | SDK300자 |
| 페이지·섹션 설명 | 12,000자 |
| 텍스트 블록 | SDK20,000자 |
| 섹션 key | 1–80자, 영문·숫자로 시작, 영문·숫자·밑줄·하이픈 |
| 지표 블록 | 1–100개, 이름160자, 유한 숫자 |
| 표 | 1–100열,0–2,000행, 열 이름160자, 문자열 셀4,000자 |
| PNG/JPEG | 개당8MiB, 한 변8192, 총16M pixels, 단일 프레임 |
| 페이지 전체 | base64 포함 JSON16MiB,100섹션·500블록·100고유이미지 |
| 태그 | 최대30개, 각100자 |
| 전송 timeout | 기본30초,0초 초과120초 이하 |
| 결과 페이지 버전 | 최대10,000 |
| 기본 프로젝트 저장 | 결과 JSON+이미지 원본 합계1GiB |

저장·요청 한도는 운영 정책에 따라 달라질 수 있습니다.1GiB는 논리적 결과 보관 합계이며 실제 DB 디스크나 청구량과 같다는 뜻은 아닙니다. base64는 이미지 크기를 늘리므로8MiB 이미지 두 장이16MiB JSON 안에 반드시 들어가지는 않습니다.

등록·조회·보고서 조합·Notion 전달 자체는 추가 AI·GPU 작업을 시작하지 않습니다. 서버 저장·전송·외부 서비스의 기존 요금은 별도입니다. 실제 AI 상담과 연구 실행은 해당 환경의 예산·권한을 따릅니다.

## 10. 자주 막히는 상황과 해결 순서

| 증상 | 확인·해결 |
| --- | --- |
| ModuleNotFoundError: luna_repro | 현재 노트북/가상환경에 SDK가 설치됐는지 확인. Colab `%pip`, 로컬 해당 Python의 `-m pip` 사용 |
| ZIP 파일을 찾을 수 없음 | Colab Files에 런타임 파일 업로드를 했는지 확인. 노트북 업로드만으로 ZIP은 생기지 않음 |
| UUID 오류 | 프로젝트 이름·키 대신 연결 화면의 UUID 사용 |
| 프로젝트 목록이 비어 있음 | 현재 계정·프로젝트 참여·운영 이용 범위를 관리자에게 확인 |
| 키를 다시 볼 수 없음 | 정상 동작. 보관한 키 사용 또는 새 키 발급 후 교체 |
| pending / connection_required | endpoint·키·timeout 형식 확인. 보존 JSON 경로 확인 후 명시 재전송 |
| authorization_required /403 | 프로젝트 UUID와 키 프로젝트 일치, 키 만료·해제, 현재 계정·참여 상태 확인 |
| transport_error | 최종 HTTPS endpoint·인터넷·서버 상태 확인. redirect 주소 사용 금지 |
| 413 또는 request_limit | 이미지 해상도/압축·선택 블록을 줄이거나 페이지 분리 |
| storage_quota | 프로젝트 저장 정책과 선택 크기 확인. 기존 자료를 임의 삭제하지 않음 |
| rate_limited /429 | retry_after가 있으면 그 초만큼 지난 뒤 직접 재시도. 자동 반복 금지 |
| NaN/Infinity 오류 | 누락·무한 값을 확인. 지표에서 제외하고 이유 설명; 표는 None 허용 |
| 표 행 길이 오류 | 모든 행의 셀 수가 columns 길이와 같은지 확인 |
| SVG/HTML 이미지 오류 | PNG/JPEG로 내보낸 작은 결과 사용 |
| source commit 오류 | 실제 소문자40/64자리 hash 사용. 모르면 생략 |
| source URL 오류 | query·인증정보·내부 주소 제거, 공개 호스트 HTTPS 영속 링크 사용 |
| 셀 링크가 다른 위치로 감 | 실제 notebook cell ID·공유 범위 확인. cell_id만으로 링크가 생성되지 않음 |
| 지표 블록이 중복됨 | 같은 섹션 추가 셀을 재실행했는지 확인. 새 Page 구성 또는 새 명시 key 사용 |
| 같은 실험이 새 페이지로 생김 | Page 생성 셀을 다시 실행하면 새 ID 생성. 복구는 sync 사용 |
| sync 결과가 빈 목록 | 올바른 outbox인지, 이미 성공 영수증이 있는지 확인 |
| request_conflict / page_conflict | 저장 요청 ID·페이지 소유자·프로젝트 일치 확인. 원본 JSON의 ID를 임의 수정해 재시도하지 않음 |
| version_limit | 기존 페이지를 보존하고 새 페이지를 만들어 설명에 이전 결과 링크 명시 |
| 팀원이 링크를 열지 못함 | 로그인·현재 프로젝트 접근·원본 보기 범위 확인. 키 공유로 우회하지 않음 |
| 보고서 저장 실패 | 섹션 수·같은 연구실 여부·원본 접근·본문 크기·동시 수정 확인 |
| Notion에 이미지가 안 붙음 | 복사 HTML 대신 허용된 연결의 Notion 직접 전달 사용 |
| Notion 대상이 없음 | 기존 Notion 연결·현재 관리 범위·대상 공유 및 삽입 권한 확인 |
| Notion 결과가 불확실 | 대상 페이지를 먼저 확인하고 원격 발행 기록 확인. 무작정 재전송하지 않음 |
| AI가 코드를 읽지 못함 | 실제 소스 접근 도구·권한·commit·파일을 별도 제공. 결과 링크가 전체 코드가 아님 |

문제 문의에는 화면 URL, 발생 시각, SDK 버전, 오류 code, 기대 결과와 실제 결과를 적습니다. 연결 키·개인정보·비공개 연구 원문·전체 환경 변수·인증 헤더는 보내지 않습니다.

## 11. 첫 실습 완료 확인

1. 오프라인 예제에서 MAE/RMSE0.5와 약0.1을 확인했습니다.
2. 실제 프로젝트 UUID와 본인 연결 키로 `published` 영수증을 받았습니다.
3. 플랫폼에서 두 결과의 지표·그래프·표·코드 출처를 확인했습니다.
4. 서로 다른 결과의 섹션을 담아 보고서를 저장했습니다.
5. 원본 결과와 보고서의 보기 범위를 확인했습니다.
6. 섹션 링크 또는 AI 검토 자료를 통해 후속 검토할 수 있음을 확인했습니다.
7. 다음에는 실제 연구에서 작은 표·그림 하나를 선택하여 같은 방식으로 등록합니다.

이 과정은 결과 등록과 보고 흐름을 익히는 실습입니다. 실제 연구의 재현성은 실행 코드·데이터·모델·환경·평가 명세를 정확히 고정하고, 별도 실행과 검토 증거를 남겨 확인합니다.

## 12. SDK 0.3.0으로 계산 줄·셀과 선택 코드를 보존하기

**파일명만 있는 예전 결과는 원래 저장된 정보가 부족한 상태입니다.** 기존 고정 버전은 덮어쓰지 않습니다. 새 결과를 등록할 때 아래 helper로 위치와 선택한 본문을 함께 넣으세요. 웹의 합성 예제를 다시 만들면 같은 예제 페이지 ID에 CPU 계산과 코드 출처를 포함한 새 버전이 추가됩니다. 이전 버전의 본문·해시·보고서 참조는 그대로 남으며 동일 내용의 반복 요청은 중복 버전을 만들지 않습니다. 휴지통의 예제는 자동 복원하지 않습니다. 공개 완성 예시에서도 각 섹션의 **계산 코드 출처 → 계산 코드 보기**로 실제 교육용 파일의 해당 줄을 열 수 있습니다.

### 24.1 무엇이 자동이고 무엇을 선택하나요?

기본 SDK는 결과를 등록한 Python 호출 위치만 기록할 수 있습니다. 결과를 계산한 앞선 함수·셀을 추측하지 않습니다. 가상 노트북 실행 프레임에서는 파일 위치가 비어 있을 수 있습니다. `source.function(...)`, `source.file(...)`, `source.notebook(...)`으로 계산 관련 위치를 직접 선택하세요. `snapshot=False`가 기본이며 코드 본문은 저장하지 않습니다. `snapshot=True`라고 명시할 때 선택한 코드만 bundle에 들어갑니다. helper 호출 자체는 파일 저장·플랫폼 전송·코드 실행을 하지 않습니다.

| 화면의 표시 | 실제 의미 |
| --- | --- |
| 결과 등록 위치 | SDK를 호출한 줄입니다. 앞서 계산한 코드와 다를 수 있습니다 |
| 사용자가 지정한 계산 코드 | 사용자가 연결한 계산 범위입니다. 실행 성공 증명은 아닙니다 |
| 함수·클래스 또는 셀 정의 | 저장된 정의의 위치입니다. 실제 호출 여부는 별도입니다 |
| 참고 코드 · 실행본 동일성 미확인 | 검토에 사용할 사본이며 과거 실행과 같은 코드인지 확인되지 않았습니다 |
| 선택한 코드 본문·해시 보존 | 고정 결과 버전에 선택 텍스트와 SHA256을 저장했습니다 |
| 등록자가 로컬 파일과 commit 일치를 관측 | 선택 파일의 바이트가 해당 로컬 Git commit과 일치했습니다. 서버가 GitHub나 실행을 독립 검증한 것은 아닙니다 |
| 링크 구성됨 · 외부 접근·실행 미검증 | 이동할 주소를 만들었습니다. 로그인 권한, 외부 서비스의 응답과 실행 결과는 확인하지 않았습니다 |

### 24.2 그대로 실행할 수 있는 Python 파일 예제

SDK 0.3.0을 설치한 뒤 아래 코드를 새 `source_example.py`에 저장하고 `python source_example.py`로 실행하세요. `__file__`을 쓰므로 노트북 셀에 그대로 붙이는 예제가 아닙니다. 세 합성 값의 MAE 0.5와 계산 함수의 실제 줄·본문을 로컬 JSON에 저장합니다. 예제 UUID는 연습용이며 네트워크·GPU·AI 호출은 없습니다. 매번 새 페이지 ID의 파일을 만들어 이전 결과를 보존합니다.

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

JSON의 `sections[0].source.provenance.snapshot.text`에서 선택한 함수만 들어갔는지 확인하세요. 코드 본문에 비밀·원문 데이터·개인정보가 있다면 전송하기 전에 제외합니다. 플랫폼에 올리려면 [설치 안내](installation-ko.md)에 따라 실제 프로젝트 UUID와 본인 연결을 설정하고 명시적으로 `publish()`를 호출해야 합니다. 등록 후 섹션의 **코드·실행 출처 → 보존된 코드 보기**에서 해당 줄로 이동합니다. 이 읽기 화면은 현재 결과 권한을 다시 검사하며 코드를 실행하지 않습니다.

기존 내려받은 `walkthrough.py`도 `python walkthrough.py --include-source`로 실행하면 지표·그림 등 관련 함수 정의를 선택해 보존합니다. 이 옵션도 기본은 로컬 저장입니다. 실제 프로젝트로 보내려면 `--project`와 `--publish`를 명시합니다.

### 24.3 helper 전체 문법과 초기값

| 호출 | 기본값과 계약 |
| --- | --- |
| `repro.source.file(path, *, root, line_start=1, line_end=None, snapshot=False, repository_url=None, role="computation")` | 실제 `.py` 파일에서 지정 범위를 선택합니다. `line_end=None`은 마지막 줄입니다. `root` 안의 파일만 가능하며 범위가 실제로 존재해야 합니다 |
| `repro.source.function(function, *, root, snapshot=False, repository_url=None)` | 실제 파일이 있는 함수 또는 클래스의 저장된 정의를 선택합니다. role은 `definition`입니다. 동적/가상 셀 정의는 직접 저장한 셀로 지정합니다 |
| `repro.source.registration(*, root, snapshot=False, repository_url=None)` | 이 helper를 부른 현재 줄을 `registration`으로 표시합니다. 계산 출처를 찾는 도구가 아닙니다 |
| `repro.source.notebook(path, cell_id, *, root, provider="jupyter", notebook_url=None, snapshot=False, repository_url=None, role="definition")` | 저장한 `.ipynb`에서 실제 ID가 일치하는 코드 셀 하나를 선택합니다. `provider="colab"`도 지원합니다. 과거 실행 동일성이 불확실하면 `role="reference"`를 사용합니다 |

`root`는 접근 범위를 명시하는 실제 디렉터리입니다. 경로와 symlink를 해석했을 때 그 밖으로 나가면 거절합니다. 디렉터리 전체를 탐색하거나 업로드하지 않습니다. 파일 하나는 최대 1 MiB, 보존 본문은 출처당 32 KiB·1,000줄, 페이지·섹션에 복사된 모든 출처를 합쳐 최대 256 KiB입니다. 페이지 source의 상속 사본도 합산하므로 필요한 섹션에만 작은 범위를 지정하세요. JSON 전체 16 MiB와 프로젝트 보관 한도도 함께 적용됩니다.

### 24.4 GitHub의 정확한 줄 링크

`root`를 Git 저장소의 실제 최상위 폴더로 지정하고 `repository_url="https://github.com/조직/저장소"`에 실제 주소를 넣습니다. helper는 로컬 Git의 HEAD와 선택 파일을 읽고 바이트가 일치할 때만 자동 고정 commit 링크를 만듭니다. Python은 `.../blob/<정확한 commit>/<파일>#L시작-L끝` 형태입니다. 수정된 파일·Git 없는 폴더·알 수 없는 상태에는 자동 고정 링크를 만들지 않으며, 선택 snapshot을 보존하면 플랫폼에서 그 내용을 계속 읽을 수 있습니다. Git remote 인증정보를 자동 수집하지 않습니다. 같은 텍스트여도 CRLF/LF 등 바이트 차이가 있으면 일치로 주장하지 않습니다.

GitHub의 노트북 파일 링크를 노트북의 정확한 실행 셀 링크라고 표시하지 않습니다. 저장된 notebook 파일과 선택 셀 본문·셀 ID를 확인할 수 있지만, 실제 실행 환경의 셀 이동은 별도 provider 주소를 사용합니다. 외부 저장소 권한은 LUNA 결과 공유와 별개입니다.

### 24.5 Colab·Jupyter의 실제 셀 선택

현재 노트북을 저장해 실행 환경에서 읽을 수 있는 `.ipynb` 사본을 준비합니다. Jupyter는 셀의 최상위 `id`, Colab은 셀 `metadata.id`를 사용합니다. 두 값은 서로 다를 수 있으며 화면상 셀 번호나 실행 순번으로 대체하면 안 됩니다. 아래는 준비한 파일과 **실제로 존재하는 ID**를 입력하는 형태입니다. 모든 파일·ID·URL은 본인의 사본에 맞춰야 합니다.

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

Colab에서는 실제 저장된 셀 ID가 확인되면 `#scrollTo=<metadata.id>`를 구성합니다. `notebook_url`은 query·기존 fragment가 없는 주소여야 합니다. helper는 Colab 내부 API로 현재 실행 셀 ID를 몰래 알아내지 않으며, 링크를 만들었다고 브라우저 이동까지 검증했다고 표시하지 않습니다. 셀 ID가 없거나 중복이면 실패합니다. 저장되지 않은 편집·다른 사본·셀 삭제 이후에는 원래 실행본과 달라질 수 있으므로 snapshot과 명확한 상태를 함께 남기세요.

`walkthrough.ipynb`의 `INCLUDE_SOURCE`는 기본 False입니다. 저장한 notebook을 실행 환경에 올리고 `SOURCE_NOTEBOOK`, `SOURCE_PROVIDER`, `SOURCE_CELL_ID`를 실제 값으로 바꾼 뒤 True로 설정하고 계산·저장 셀을 실행하세요. `SOURCE_NOTEBOOK_URL=None`이면 외부 실행 링크를 추측하지 않습니다. 노트북 출력·첨부·실행 중 전역변수는 선택 코드 snapshot에 포함하지 않습니다.

### 24.6 기존 결과, AI, 복구에서 확인할 것

기존 결과의 파일명·줄 정보는 그대로 보존하고 새 코드 snapshot이 있는 척하지 않습니다. 페이지 고정 버전마다 해당 snapshot을 열 수 있습니다. 일반 AI 컨텍스트·자료 내려받기·Notion 전달은 코드 본문을 자동 포함하지 않습니다. 보고서 AI에서 **코드 본문 포함**을 선택한 경우에만 현재 권한으로 읽은 선택 snapshot을 분석 근거로 추가합니다. 코드가 없으면 없다고 표시하며 외부 URL을 임의로 가져오지 않습니다. 과거 실행 동일성, 데이터 일치, 독립 재현과 연구 성공은 별도 검증 사항입니다.

`invalid_source_snapshot`이면 선택 줄·본문·해시를 다시 구성하고, `source_snapshot_limit`이면 작은 함수·셀만 선택하세요. 휴지통 결과의 SDK 재전송은 `result_trashed`로 보류되며 자동 복원되지 않습니다. 플랫폼에서 본인 결과를 복원한 다음 저장된 outbox를 명시적으로 다시 전송합니다. 권한 철회·휴지통 상태에서는 예전 코드 링크도 현재 권한 검사에 따라 열리지 않습니다.
