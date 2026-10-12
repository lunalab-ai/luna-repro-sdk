# 재현성 결과 등록 예제 / Result-page examples

- `quickstart.ipynb`: SDK 0.3.0 설치·합성 결과 선택·로컬 HTML 미리보기. 브라우저 연결과 전송은 별도 기본 꺼짐입니다. Installation, synthetic selection and local preview; separate connection/publication flags default off.
- `auto_select.py`: 표준 라이브러리 CPU 실습입니다. 새 로컬 폴더에 미리보기·JSON·선택 규칙을 저장하며 연결·전송하지 않습니다. Standard-library CPU example saves preview, bundle and selection rule in a new local folder without connecting or publishing.
- `docs/selection-ko.md`, `docs/selection-en.md`: 일반 연구 객체·체크 UI·capture·명시 자동 규칙·출처 한계를 안내합니다. Scientific objects, checkboxes, capture, explicit automatic rules and source limits.

이 폴더에는 실제 연구 원본·모델·데이터·비밀을 넣지 않습니다. `toy.py`는 결정적 합성 CPU 예제, `pasa_adapter.py`는 사용자가 지정한 기존 출력에서 일부 결과를 읽는 어댑터입니다. 업로드와 실제 Pasa 실행은 별개입니다.

## 처음부터 따라하기 / Start here

[국문 설명서](https://lunalab-ai.com/workspace/repro/guide/?lang=KO) · [English handbook](https://lunalab-ai.com/workspace/repro/guide/?lang=EN)

`walkthrough.ipynb`는 설치·오프라인 계산·저장·선택적 전송·재시도를 셀별로 안내합니다. 기본 `PUBLISH=False`, `RETRY=False`이므로 전체 셀을 실행해도 전송하지 않습니다. 실제 프로젝트 UUID를 설정하고 계산/저장 셀을 다시 실행한 뒤, 전송 셀만 명시적으로 활성화하세요. 연결 키는 숨김 입력으로 받습니다. 첫 설치 셀은 SDK 0.3.0이 없을 때만 공개 wheel을 받으므로 이 단계에는 네트워크가 필요합니다.

`walkthrough.py`도 기본 오프라인입니다. 프로젝트 환경에 SDK를 설치한 뒤 실행합니다.

```bash
python examples/walkthrough.py
# 실제 프로젝트 UUID와 세션 endpoint를 준비한 경우에만:
python examples/walkthrough.py --project YOUR-PROJECT-UUID --publish
```

명령은 압축을 푼 `luna-repro-sdk/` 또는 Git checkout 루트에서 실행합니다. `.luna-repro/walkthrough/새실행폴더/`에 baseline/corrected JSON을 저장하며, 전송 시 그 폴더의 `outbox/`를 사용합니다. six-value offset 예제의 MAE/RMSE는 0.5와 약 0.1입니다. 아래 `toy.py`와 브라우저 데모의 잡음 신호·이동평균 수치와는 별개의 합성 예제입니다.

`walkthrough.ipynb` explains installation, offline computation, saving, optional publication and explicit retry one cell at a time. The installation cell uses the network only when SDK 0.3.0 is absent. After installation, default calculation/save cells are offline; `PUBLISH=False` and `RETRY=False` prevent result transmission. Set your real project UUID, rerun computation/saving, then explicitly enable only the publication cell. Keys are entered through a hidden prompt.

After SDK installation, run `walkthrough.py` without flags for offline practice. Add your real `--project` UUID and `--publish` only when you intend transmission and have configured the session endpoint. In the downloadable ZIP use `examples/walkthrough.py`. Each run preserves files under a new `.luna-repro/walkthrough/` subdirectory with its own outbox. Six-value correction yields MAE/RMSE 0.5 and approximately 0.1; these are a different synthetic example from the noisy-signal/moving-average toy below.

## 두 페이지 합성 데모

프로젝트 환경에 [SDK](../README.md)를 설치한 뒤 실행합니다.

플랫폼에서 내려받은 SDK ZIP을 풀었다면 SDK 안내는 상위 `README.md`에 있습니다. 압축을 푼 `luna-repro-sdk/`에서 아래 명령을 실행하세요.

```bash
python examples/toy.py --project YOUR-PROJECT-UUID --output .luna-repro/toy
```

잡음 신호와 이동평균 결과의 RMSE를 실제 계산하고, PNG 그래프·일부 표가 포함된 **두 개의 JSON 결과**를 저장합니다. seed는 `20261011`입니다. 데이터와 계산 결과는 결정적이며 새로운 실행의 page/run/request UUID는 달라질 수 있습니다. 이 수치를 Pasa·Teeth3DS+ 연구 성능으로 해석하지 않습니다.

프로젝트 토큰·HTTPS endpoint를 세션 환경에 설정한 뒤 `--publish`를 추가하면 실제 플랫폼에 명시적으로 등록합니다. 플랫폼에서 두 페이지의 섹션을 모아 하나의 보고서를 구성하고, 선택한 Notion 대상으로 전달하는 흐름을 확인할 수 있습니다. GPU·외부 AI 비용은 발생시키지 않습니다. 플랫폼/네트워크/저장 비용은 환경 정책을 따릅니다.

## 마지막 셀과 실행 중 누적

- [last_cell.ipynb](last_cell.ipynb): 연구 코드가 먼저 결과를 만들고, 마지막 셀에서 등록합니다.
- [incremental.ipynb](incremental.ipynb): 첫 셀에서 페이지를 준비하고 중간 결과를 누적한 뒤 등록합니다.

노트북은 소스·출력에 토큰을 포함하지 않습니다. 기본 예제는 오프라인 JSON 저장까지 실행하며, 전송은 `publish()` 셀을 명시적으로 실행합니다. 연결 설정은 SDK 안내를 따릅니다. 생성된 파일에는 선택한 연구 내용이 있으므로 비공개로 보관하세요.

## Pasa 마지막 셀

기존 노트북·추론·학습 셀을 바꾸지 않고, `pasa_adapter.py`를 노트북에서 import 가능한 코드 폴더에 둡니다. `RUN_DIR`는 기존 Pasa 코드가 생성한 출력 폴더입니다.

```python
from pasa_adapter import build_page

page = build_page(RUN_DIR, project=project_id, notebook_url=notebook_url)
receipt = page.publish()
print(receipt.get("url") or receipt["message"])
```

또는 연결 없이 JSON만 먼저 생성합니다.

```bash
python examples/pasa_adapter.py SELECTED_RUN_FOLDER --project YOUR-PROJECT-UUID --output .luna-repro/pasa-result.json
```

어댑터는 `run_manifest.json`, `camera_checks.json`, manifest에 명시된 method/case별 `renders/003_render.png`, `evaluation/comparison.csv`만 선택합니다. 경로 탈출·선택 폴더 밖으로 향하는 파일 링크는 거부합니다. 데이터셋·모델 checkpoint·전체 소스·전체 manifest는 전송하지 않습니다. GitHub/Drive를 자동 다운로드하거나 inference/training을 실행하지 않습니다.

`origin=imported`로 표시합니다. manifest의 완료 상태는 **기록된 실행 종료**이고 연구 검증이 아닙니다. 카메라 진단 미통과는 그대로 표시합니다. GT 설정이 확인되지 않거나 비교 표가 없으면 평가 상태는 `not_run`입니다. 실제 해당 실행에 GT를 설정해 평가했고 유효한 비교 표가 있을 때만 `gt_available=True`(CLI `--gt-available`)를 명시합니다. 이 선언도 독립 재실행 검증과 다릅니다.

동일 manifest를 다시 가져오면 프로젝트+manifest SHA256으로 같은 page/run ID를 얻습니다. 실제 코드 커밋·노트북 스냅샷을 알고 있다면 `repository_url`, `commit`, `notebook_sha256`을 명시하세요. 검토한 저장소의 현재 커밋을 과거 실행 코드라고 대신 기록하지 않습니다. 기록에 없는 정량 수치·시간·VRAM은 만들어내지 않습니다.

## English

Install the SDK, then run `toy.py --project PROJECT-UUID`. For the ZIP, run commands from the extracted `luna-repro-sdk/` root; SDK instructions are in its README. The toy computes deterministic noisy-signal and moving-average metrics on CPU and saves two separate result pages with PNG charts and tables. Add `--publish` only when you want to send them using the session endpoint/token. These synthetic metrics are not Pasa or Teeth3DS+ results.

The two clean notebooks demonstrate final-cell registration and incremental collection. They have no saved outputs or credentials. Offline `save()` works without a platform connection; explicit `publish()` needs the configured endpoint/token.

The Pasa adapter reads selected existing outputs under the chosen run directory only. It never runs inference/training or fetches repositories, models or datasets. Import is labeled as imported evidence, failed camera checks stay visible, and evaluation remains `not_run` unless the caller explicitly confirms ground truth and a populated comparison CSV exists. Pinned source identities must describe the code actually used, not merely a repository revision reviewed later.
