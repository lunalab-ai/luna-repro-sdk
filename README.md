# LUNA Repro SDK

[English](https://github.com/lunalab-ai/luna-repro-sdk/blob/v0.2.1/README.en.md) · [상세 가이드](https://lunalab-ai.com/workspace/repro/guide/?lang=KO) · [브라우저 데모](https://lunalab-ai.com/workspace/repro/demo/?lang=KO)

Python·Colab·자체 서버의 기존 연구 코드에서 선택한 결과를 LUNA 플랫폼에 정리하는 작은 SDK입니다. 계산·GPU·AI를 실행하거나 폴더를 자동 업로드하지 않습니다. 패키지는 `luna-repro`, import는 `luna_repro`, CLI는 `luna-repro`입니다. Python 3.10 이상이며 런타임 의존성이 없습니다.

## 설치

프로젝트 가상환경에서 버전을 고정하여 설치하세요. PyPI 설치 명령이 아니라 이 저장소의 릴리스 wheel을 사용합니다.

```bash
python -m pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.2.1/luna_repro-0.2.1-py3-none-any.whl
python -c "import luna_repro; print(luna_repro.__version__)"
```

`0.2.1`이 표시되어야 합니다. Colab에서는 첫 줄의 `python -m pip` 대신 `%pip`를 사용하세요. 예제는 pip 설치와 별개입니다. 릴리스의 `luna-repro-sdk-0.2.1.zip`을 풀면 `luna-repro-sdk/examples/`에서 노트북과 Python 파일을 열 수 있습니다. ZIP 자체도 `python -m pip install ./luna-repro-sdk-0.2.1.zip`으로 설치할 수 있으며 빌드 도구 설치에 인터넷이 필요할 수 있습니다. 오프라인 설치에는 wheel을 권장합니다.

## 먼저 로컬에서 확인하기

아래 코드는 그대로 실행할 수 있습니다. 예제 프로젝트 UUID이며 네트워크 전송은 없습니다. 새 파일을 만들어 이전 결과를 보존합니다.

```python
from pathlib import Path
import uuid
import luna_repro as repro

target = [0.0, 1.0, 2.0]
measured = [value + 0.5 for value in target]
mae = sum(abs(a - b) for a, b in zip(target, measured)) / len(target)
page = repro.page("12345678-1234-5678-1234-567812345678", "첫 합성 결과",
    evidence={"origin": "synthetic", "execution_status": "completed", "evaluation_status": "completed"})
page.section("metrics", "오차").metrics({"MAE": mae, "samples": len(target)})
page.section("rows", "입력과 예측").table(["target", "measured"], list(zip(target, measured)))
destination = Path(".luna-repro") / (str(uuid.uuid4()) + ".json")
print(page.save(destination))
```

MAE는 `0.5`입니다. `python examples/walkthrough.py`는 MAE/RMSE `0.5 → 약 0.1`인 두 결과를 로컬 저장합니다. `toy.py`와 브라우저 데모는 다른 잡음 신호·이동평균 실습이며 숫자를 서로 비교하지 마세요. 모든 예제의 기본 실행은 공개·비공개 플랫폼 등록을 하지 않습니다.

## 명시적으로 플랫폼에 보내기

프로젝트의 **재현성 연결**에서 본인의 프로젝트 UUID와 연결 키를 준비합니다. 실제 UUID·플랫폼 주소를 넣고 필요한 결과만 선택한 후 별도 셀에서 실행합니다. 기본 `PUBLISH=False`를 확인 후 변경하세요.

```python
import getpass
import os
import uuid

PUBLISH = False
if PUBLISH:
    project_id = str(uuid.UUID(input("Actual project UUID: ").strip()))
    if project_id == "12345678-1234-5678-1234-567812345678":
        raise ValueError("Use your actual permitted project UUID")
    os.environ["LUNA_REPRO_ENDPOINT"] = "https://lunalab-ai.com"
    os.environ["LUNA_REPRO_TOKEN"] = getpass.getpass("Project connection key: ")
    # Rebuild the selected result with the actual project; credentials are not serialized.
    published_page = repro.page(project_id, "첫 합성 결과", evidence=page.evidence)
    published_page.section("metrics", "오차").metrics({"MAE": mae, "samples": len(target)})
    receipt = published_page.publish()
    print(receipt.get("url") if receipt["status"] == "published" else receipt["message"])
```

`status="published"`와 URL이 서버 수신 확인입니다. `pending`은 로컬 outbox에 보존되었지만 등록이 완료되지 않았다는 뜻입니다. 토큰은 소스·출력·명령 인수·URL에 넣지 마세요. outbox에는 선택한 연구 내용이 있으므로 비공개로 보관합니다.

```bash
python -m luna_repro publish selected-result.json
python -m luna_repro sync --outbox .luna-repro/outbox
```

CLI는 환경 변수 `LUNA_REPRO_ENDPOINT`, `LUNA_REPRO_TOKEN`을 사용합니다. 자동 반복 전송·자동 휴지통 복원은 없습니다. `result_trashed`는 플랫폼에서 복원 후 명시 재전송, `authorization_required`는 권한·토큰 확인, `storage_quota`는 보관 한도 확인, `rate_limited`는 `retry_after` 이후 수동 재시도를 뜻합니다.

## 코드 출처와 한계

자동 출처는 등록 호출 위치이며 실제 계산 줄·노트북 셀을 추측하지 않습니다. `repro.source.file/function/registration/notebook`에 실제 `root`와 대상을 지정합니다. `snapshot=False`가 기본이고 `snapshot=True`일 때 선택 코드만 포함합니다. Colab `metadata.id`와 Jupyter `id`를 구분하며, 링크 구성은 외부 접근·과거 실행 동일성·독립 재현 검증을 뜻하지 않습니다.

이미지 최대 8 MiB, JSON 묶음 16 MiB, 표 2,000행/100열입니다. 출처 파일은 1 MiB, 선택 코드 32 KiB·1,000줄/출처, 상속 포함 256 KiB/페이지입니다. `walkthrough.py --include-source`로 선택 계산 함수 보존을 연습할 수 있습니다. 노트북은 `INCLUDE_SOURCE=False`가 기본입니다. 실제 파일·셀 ID를 설정한 뒤 명시적으로 선택하세요.

SDK `0.2.1`은 `luna.repro.page.v1` 및 선택 확장 `luna.repro.source.v1`을 사용합니다. 플랫폼 버전과 SDK 버전은 독립적입니다. 서버의 현재 프로젝트 권한·수신 검사·한도가 최종 기준입니다. 보고서·Notion·AI 기능은 플랫폼에서 수행하며 SDK가 원격 연구 실행 또는 코드 개선을 자동 수행하지 않습니다.

## 문서·개발·릴리스 검증

[설치 안내](https://github.com/lunalab-ai/luna-repro-sdk/blob/v0.2.1/docs/installation-ko.md)와 [전체 한영 매뉴얼](https://github.com/lunalab-ai/luna-repro-sdk/tree/v0.2.1/docs)을 제공합니다. 별도 가이드 ZIP은 매뉴얼과 실습 파일이며 SDK installer는 포함하지 않습니다. Git checkout에서 다음 검사를 실행합니다. ZIP에 개발 검사 파일이 없는 것은 의도된 배포 구분입니다.

```bash
python -m unittest discover -s tests -v
python scripts/audit_public.py
python scripts/build_release.py --output dist
```

빌드는 프로젝트 가상환경의 `setuptools==80.9.0`, `wheel==0.45.1`을 사용합니다. 자동 유료 워크플로가 필요하지 않습니다. 릴리스 파일의 `SHA256SUMS`로 다운로드 무결성을 확인할 수 있습니다. SHA256은 파일 동일성 확인이며 독립 서명이나 연구 검증이 아닙니다. MIT 범위와 외부 자료의 별도 권리는 LICENSE를 확인하세요.
