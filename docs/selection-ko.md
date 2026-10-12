# 결과 자동 추천·선택·연결 — SDK 0.3.0

SDK는 연구 코드가 실행되는 Python/Colab 프로세스 안에서 동작합니다. 결과 후보를 로컬에서 찾고 사람이 확인한 내용만 LUNA 프로젝트로 보냅니다. `select()` 자체는 AI 호출이나 네트워크 전송을 하지 않습니다. 계산의 성공 여부를 자동 판정하지 않으며 모델·데이터셋·작업 폴더를 탐색하지 않습니다.

## 1. 첫 셀: 설치와 프로젝트 연결

다음 설치 URL은 버전이 고정되어 있습니다. Colab에서는 `%pip`로 실행합니다. 기존 버전이 이미 import된 상태라면 설치 후 런타임을 재시작하세요. 새 프로젝트 생성은 플랫폼에서 진행합니다.

```bash
python -m pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.3.0/luna_repro-0.3.0-py3-none-any.whl
```

```python
import luna_repro as repro

CONNECT = False  # 실제 프로젝트 UUID 입력·검토 후에만 True
project_id = "12345678-1234-5678-1234-567812345678"  # 합성 실습용
if CONNECT:
    if project_id == "12345678-1234-5678-1234-567812345678":
        raise ValueError("실제 참여 프로젝트 UUID를 입력하세요")
    connection = repro.connect(project_id, label="Colab", open_browser=False)
else:
    repro.configure(project_id)  # 네트워크 없이 로컬 미리보기 준비
```

연결하면 확인 코드와 브라우저 승인 링크가 표시됩니다. LUNA에서 로그인하고 **프로젝트·요청 종류·확인 코드**를 대조해 승인하세요. Colab에서 링크를 직접 눌러도 됩니다. SDK는 최대 10분 동안 승인만 기다리며 연결 키를 메모리에 둡니다. 응답·노트북 출력·선택 규칙에는 키를 넣지 않습니다. 런타임 재시작 후에는 다시 연결합니다. 같은 프로젝트의 아직 만료되지 않은 메모리 연결은 재사용할 수 있지만 실제 전송 때 서버가 현재 권한과 키 폐기를 다시 확인합니다.

`connect(project, *, endpoint="https://lunalab-ai.com", label=None, timeout=600, open_browser=True, force=False)`는 비밀 없는 `project_id`, `project_title`, `expires_at`, `reused`를 반환합니다. `label`은 `Python`, `Colab` 또는 `Jupyter`, `timeout`은 1~600초입니다. 자동 브라우저 열기가 불편하면 `open_browser=False`, 새 승인을 의도하면 `force=True`를 사용합니다. 승인 거절·시간 초과·중단은 결과 전송이 아닙니다.

연결 키 직접 입력도 유지합니다. 키를 하드코딩하지 말고 `getpass.getpass()` 값을 `configure(project, endpoint=..., token=...)`로 전달하세요. `configure`는 메모리 설정만 바꾸며 디스크·네트워크 작업을 하지 않습니다. `outbox=`로 보존 폴더를 선택할 수 있습니다. `repro.clear()`는 로컬 키만 잊습니다. 서버 키 폐기는 플랫폼 연결 관리에서 별도로 합니다. HTTPS 및 개발용 loopback HTTP만 허용하며 리다이렉트를 따라 키를 전달하지 않습니다.

## 2. 마지막 셀: 변수를 하나씩 지정하지 않아도 됩니다

```python
metrics = {"MAE": 0.5, "samples": 3}
comparison = [[0.0, 0.5], [1.0, 1.5], [2.0, 2.5]]
failed_check = {"passed": False, "maximum_error": 0.5}
selected = repro.select(purpose="error comparison")
```

`select()`는 호출한 셀·함수의 로컬 이름 공간만 살펴봅니다. 노트북에서는 보통 해당 런타임의 사용자 변수입니다. 함수 안에서는 그 함수의 로컬 변수만 찾으므로 필요한 값은 `namespace={"metrics": metrics}`로 직접 지정할 수 있습니다. 1,000개 이름·100개 후보를 넘으면 범위를 좁히라는 오류가 납니다. `_`로 시작하는 이름, token/secret/password/credential/key 계열 민감 이름, 임의 클래스·모듈·함수·중첩 객체는 제외합니다. 일반 문자열은 자동 후보에서 제외합니다. 이름 필터가 완전한 개인정보 탐지기는 아니므로 표·그림의 내용도 직접 확인해야 합니다.

`purpose=`는 후보 이름과 지원하는 지표 이름·안전한 표 열 이름의 단순 일치로 순서를 정합니다. 의미를 이해하는 AI, 정확도 검증 또는 좋은 결과만 고르는 기능이 아닙니다. 맞지 않는 후보와 실패·경고도 목록에 남습니다. 추천 이유가 표시되고 사용자가 체크를 바꿉니다. 작은 지원 객체는 기본 체크되지만 **전송 버튼을 누르기 전에는 보내지 않습니다**.

`i`, `epoch`, `batch_size`, `learning_rate` 같은 알려진 설정·반복 수치는 후보에 남기되 기본 체크를 해제합니다. `loss`, `accuracy`, `failed`, `epoch_loss` 같은 결과·실패 후보는 유지합니다. 이름 기반 추정이므로 최종 선택은 사용자가 확인합니다.

노트북에 `ipywidgets`가 설치되어 있으면 체크박스 → 제목·설명·순서·변환 옵션 → **미리보기** → **검토한 결과 전송**을 사용합니다. 옵션은 JSON으로 입력합니다. 예: `{"rows": 100, "index": true}`. 체크나 제목을 바꾸면 전송 버튼이 다시 잠기며 새 미리보기가 필요합니다. ipywidgets가 없거나 일반 `.py`라면 후보 이름·이유만 콘솔에 표시합니다. 값·키는 콘솔에 자동 출력하지 않습니다. 다음 코드로 동일한 과정을 진행하세요.

```python
selected = repro.select(namespace={"metrics": metrics, "comparison": comparison,
                                  "failed_check": failed_check}, show=False)
selected.choose("metrics", "comparison", "failed_check")
selected.option("comparison", title="입력과 예측", columns=["target", "predicted"])
selected.edit(title="방법 비교", description="합성 CPU 예제", order=["metrics", "failed_check", "comparison"])
html_text = selected.preview("preview.html")
selected.save("selected.json")
```

`preview()`는 독립 HTML 문자열을 반환하고 경로가 있으면 저장합니다. 외부 스크립트·이미지 서버를 사용하지 않습니다. 이 HTML과 JSON에는 선택한 내용이 들어 있으므로 비공개 파일로 취급하세요. 프로젝트 연결 전에도 후보 목록은 볼 수 있지만 내용 미리보기·저장은 실제 또는 합성 프로젝트 UUID 설정이 필요합니다.

첫 미리보기에서 선택값을 변환·고정합니다. 이후 원본 DataFrame·그림·변수가 바뀌어도 같은 `selected.publish()`는 미리 본 묶음과 요청 ID를 보냅니다. `.choose()`, `.option()`, `.edit()`로 수정하면 다시 고정합니다. 새 실행은 새 `select()`를 호출하세요. 미리보기 후 프로젝트가 바뀌면 전송을 거절합니다.

```python
PUBLISH = False
if PUBLISH:
    receipt = selected.publish()
    print(receipt)  # status=published와 URL인지 확인
```

`publish(strict=False, timeout=30)`는 먼저 outbox에 보존합니다. 통신 실패 등은 `pending`, `outbox_path`, 안전한 오류 코드로 돌아옵니다. `strict=True`면 같은 로컬 보존 후 예외를 발생시킵니다. 기본 outbox는 `.luna-repro/outbox`이고 성공 영수증도 삭제하지 않습니다. 이 메서드는 백그라운드 재시도를 하지 않습니다. 재전송은 동일 Selection 또는 기존 `repro.sync(..., endpoint=..., token=...)`/CLI를 명시적으로 사용하세요. 메모리 연결 설정은 다른 Python 프로세스의 CLI로 전달되지 않습니다.

## 3. 결과를 이미 알고 있다면 명시형 사용

`repro.publish(fig, df, metrics, title="방법 비교")`는 **즉시 전송을 요청하는 명시형**입니다. 기본 후보 추천을 다시 묻지 않습니다. 지원 객체를 같은 규칙으로 변환하고 outbox에 먼저 보존합니다. 자동 검색을 원하면 `select()`를 사용하세요. `publish()`를 인자 없이 호출하면 오류입니다. 직접 넘긴 문자열은 텍스트, bytes는 PNG/JPEG로 처리합니다.

기존 `page = repro.page(project, title)`와 `page.section(...).metrics/table/image/figure/text`는 계속 사용할 수 있습니다. `repro.publish(page)`는 페이지·실행 ID, 증거 상태, source, section을 유지하고 현재 메모리 연결을 사용합니다. Page의 프로젝트와 연결 프로젝트가 다르면 거절합니다. 기존 Page 자체의 `page.publish()`, `page.save()`와 v1 프로토콜도 유지합니다. 결과 추가·누적과 실행·평가 상태의 정확한 기록은 기존 Page API로 직접 구성할 수 있습니다. 간편 API는 연구 성공이나 completed 상태를 자동 선언하지 않습니다.

## 4. 지원 객체와 변환 기준

| 객체 | 기본 표현과 명시 옵션 |
| --- | --- |
| 유한 숫자, 작은 이름→숫자 dict | 지표. bool·비유한 수치가 섞이면 의미가 보이는 2열 표 |
| list/tuple 행, 1차원 목록 | 표. `columns=[...]`로 제목 지정; 직사각형, 최대 100열 |
| pandas DataFrame/Series | 표. 인덱스 기본 포함, `index=False`로 제외; `columns=[...]`로 열 선택 |
| NumPy ndarray | 0차원 수치, 1·2차원 표. object dtype은 거절 |
| matplotlib Figure | 현재 캔버스의 PNG; 그래프 의미·실험 성공을 해석하지 않음 |
| PIL Image 및 공식 PNG/JPEG decoder 객체 | PNG. 선택 후 실제 픽셀 읽기 |
| pathlib.Path PNG/JPEG | 추천 기본 해제, 선택 후 해당 파일 하나만 읽기 |
| Plotly Figure | 추천 기본 해제. 설치된 호환 정적 exporter가 있을 때 PNG; 브라우저·exporter 자동 설치 없음 |
| torch.Tensor | 추천 기본 해제. `allow_cpu=True`가 있을 때만 detach→CPU 복사→NumPy 변환; GPU 비용·복사 가능성 직접 검토 |

지원 패키지를 SDK가 자동 설치하거나 import해서 후보를 찾지 않습니다. 실제 연구 코드가 이미 사용하는 객체만 인식합니다. ipywidgets 표시는 선택 UI 요청 때만 선택적으로 사용합니다. 임의 사용자 서브클래스·property·repr를 호출해 타입을 추측하지 않습니다. 표 안의 지원하지 않는 사용자 객체도 문자열로 바꾸지 않고 거절합니다.

표 최대 2,000행·100열, 일반 배열 최대 200,000원소, 이미지 캔버스 최대 16백만 픽셀, 개별 PNG/JPEG 8 MiB, 전체 JSON 묶음 16 MiB입니다. 큰 표를 자동 생략하지 않습니다. `selected.option("table", rows=100)`처럼 앞부분을 명시 선택하면 전체 행 수와 선택 범위를 설명 블록에 남깁니다. pandas 인덱스도 100열 한도에 포함됩니다. 날짜는 ISO 8601, None/pandas NA·NaT는 null, NaN/±Infinity는 문자열 `NaN`, `+Infinity`, `-Infinity`입니다. 비유한 지표를 유한 숫자로 조작하지 않습니다.

배열의 이미지 여부는 자동 단정하지 않습니다. `as_image=True`와 `layout="HWC"` 또는 `"CHW"`를 선택하세요. uint8 이외에는 `value_range=[0,1]`처럼 표시 범위도 필요합니다. 비유한 값·범위 밖 값은 거절하며 몰래 clipping하지 않습니다. 색 공간·의학적 표시 기준을 자동 결정하지 않습니다.

```python
# image_array는 사용자의 실제 ndarray입니다. 필요한 경우에만 선택하세요.
USE_IMAGE = False
if USE_IMAGE:
    images = repro.select(namespace={"render": image_array}, show=False)
    images.choose("render").option("render", as_image=True, value_range=[0, 1], layout="HWC")
    images.preview("image-preview.html")
```

## 5. 실행 중 닫히는 그림과 경고

```python
CAPTURE_EXAMPLE = False  # matplotlib가 있는 환경에서만 선택
if CAPTURE_EXAMPLE:
    import matplotlib.pyplot as plt
    with repro.capture(max_figures=10, max_bytes=8 * 1024 * 1024) as captured:
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 0])
        plt.close(fig)
    selected_capture = captured.select(title="선택 범위의 그림", show=False)
    selected_capture.preview("capture-preview.html")
```

이 범위 안의 pyplot `show()`/`close()`에서만 그림을 보존합니다. 범위 밖 출력·일반 파일·stdout/stderr·임의 HTML·Plotly display·이미 닫힌 과거 그림은 소급 수집하지 않습니다. 같은 PNG는 중복 제거합니다. 한도 초과·변환 실패 횟수와 경고 개수·범위 실패 여부도 후보에 포함합니다. 경고 메시지·파일 경로·예외 본문은 저장하지 않습니다. 예외를 숨기지 않고 그대로 다시 발생시킨 뒤 hook을 복원하므로 실패 후 검토하려면 호출 측에서 예외를 처리하세요. 동시·중첩 capture는 거절합니다. 다른 스레드의 그림 수집은 지원하지 않습니다. capture는 프로그램 전체 추적기나 자동 게시 기능이 아닙니다.

## 6. 선택 규칙 저장과 명시적 자동 전송

```python
selected.save_rule("selection-rule.json")  # 기본 자동 전송 금지
review_again = repro.select(namespace={"metrics": metrics, "comparison": comparison,
                                     "failed_check": failed_check}, rule="selection-rule.json", show=False)
```

규칙에는 프로젝트 UUID, 선택 이름·타입·순서·제목·설명·변환 옵션만 저장합니다. 결과값·키·전체 namespace·코드 원문을 저장하지 않습니다. 파일에 직접 넣는 제목·설명에도 민감한 정보를 쓰지 마세요. 필요한 이름이 없거나 타입·프로젝트가 바뀌면 조용히 대체하지 않고 멈춥니다. 같은 타입의 의미나 단위가 바뀌는 것은 자동 검출하지 못하므로 연구 변경 시 규칙을 다시 검토하세요.

자동 전송은 **저장 시 `auto_publish=True`와 실행 시 `auto=True`가 모두 필요**합니다. 호출 한 번에 새 묶음 한 번만 보내고, 실패를 자동 재시도하거나 학습 루프·예약·AI를 시작하지 않습니다. 같은 이름 아래 새 값이 들어오면 그 값을 전송할 수 있으므로 신뢰할 수 있는 반복 실행에서만 사용하세요. 중지하려면 `auto=False`로 실행하거나 규칙을 자동 전송 없이 다시 저장하세요.

자동 실행 후 `run_selection.receipt`에서 실제 `published`/`pending` 상태를 확인합니다. 전송 전에는 `receipt`가 None입니다.

```python
ENABLE_AUTOMATIC_SEND = False
if ENABLE_AUTOMATIC_SEND:
    selected.save_rule("approved-rule.json", auto_publish=True)
    run_selection = repro.select(namespace={"metrics": metrics, "comparison": comparison,
                                            "failed_check": failed_check}, rule="approved-rule.json", auto=True)
```

## 7. 출처·AI·복구 경계

Python 파일에서는 간편 API 호출 파일명·줄을 등록 위치로 기록합니다. 이는 값을 계산한 줄, 실행 경로, causal provenance를 보장하지 않습니다. 동적 셀의 실행 카운터를 실제 셀 ID로 만들어내지 않습니다. 정확한 줄/셀·commit·선택 코드 보존은 기존 `repro.source.file/function/notebook(..., snapshot=True)`와 `sources={"metrics": source_ref}` 또는 Page section source를 사용하세요. source의 계산/정의/등록/참고 역할을 사실에 맞게 지정합니다. 링크 구성과 commit 일치는 실행 당시 일치·독립 재현·외부 접근 보장이 아닙니다.

선택 요약 `selected.summary()`는 이름·종류·크기·추천 이유만 로컬 반환합니다. SDK는 이 요약을 AI에 자동 전송하지 않으며 별도 AI 키·예산을 만들지 않습니다. 게시 후 플랫폼의 보고서 AI에서 자료·코드 포함 여부·예상 사용량·초안을 따로 검토합니다. 플랫폼 AI 사용량과 Colab/GPU 실행비는 SDK 설치·로컬 추천과 별개입니다.

`pending`은 실패한 결과가 사라졌다는 뜻이 아닙니다. outbox 원본을 보존하고 권한·저장 한도·네트워크를 확인한 뒤 명시 재시도하세요. `result_trashed`는 플랫폼에서 원래 결과를 복원한 후 재시도하며 SDK가 휴지통을 몰래 되살리지 않습니다. 브라우저 승인 오류와 연구 실행 실패도 구분하세요. 문제 보고에는 SDK 버전·안전한 오류 코드·합성 최소 예제만 사용하고 키·연구 JSON·원문·실제 프로젝트 ID를 공개 이슈에 올리지 마세요.
