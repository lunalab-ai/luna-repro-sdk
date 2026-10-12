# SDK 0.2.1 설치와 첫 실행

[SDK 사용법 및 전체 API](usage-ko.md) · [English](installation-en.md)

Python 3.10 이상을 사용합니다. `luna-repro`는 설치 이름, `luna_repro`는 import 이름입니다. 설치·합성 예제·실제 플랫폼 전송은 각각 다른 단계입니다. SDK 자체는 무료 실행 도구이며 유료 AI/GPU를 자동 호출하지 않습니다. 사용하는 연구 서버·데이터·플랫폼 서비스의 비용은 별개입니다.

## Windows PowerShell

새 연습 폴더에서 실행하세요. 이미 있는 환경을 덮어쓰지 않습니다.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.2.1/luna_repro-0.2.1-py3-none-any.whl
.\.venv\Scripts\python.exe -c "import luna_repro; print(luna_repro.__version__)"
```

## Linux 또는 자체 서버

```bash
python3 -m venv .venv
.venv/bin/python -m pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.2.1/luna_repro-0.2.1-py3-none-any.whl
.venv/bin/python -c "import luna_repro; print(luna_repro.__version__)"
```

이는 설치 안내이며 해당 서버에서 직접 실행 검증했다는 뜻은 아닙니다. 연구 코드의 선택 라이브러리는 그 프로젝트 환경에서 별도로 설치하세요.

## Google Colab

1. [walkthrough.ipynb](https://github.com/lunalab-ai/luna-repro-sdk/blob/v0.2.1/examples/walkthrough.ipynb)를 내려받아 Colab에서 엽니다.
2. 별도 설치 셀에서 아래 한 줄을 실행합니다. 설치에 네트워크가 필요합니다.

```python
%pip install https://github.com/lunalab-ai/luna-repro-sdk/releases/download/v0.2.1/luna_repro-0.2.1-py3-none-any.whl
```

3. `import luna_repro; print(luna_repro.__version__)`가 `0.2.1`인지 확인합니다.
4. 기본 `PUBLISH=False`, `INCLUDE_SOURCE=False`를 그대로 두고 계산·저장 셀을 실행합니다. MAE/RMSE는 0.5와 약0.1이며 JSON 경로가 출력됩니다. Colab의 파일 패널에서 결과를 직접 내려받으세요. 런타임 파일은 세션 종료로 사라질 수 있습니다.
5. 실제 전송은 실제 프로젝트 UUID를 설정하고 숨김 입력으로 연결 키를 넣은 뒤 명시적으로 선택합니다. 실습 UUID를 전송하지 마세요. `published`를 확인하기 전 완료로 보지 않습니다.

## 예제 ZIP·오프라인 설치·해시

릴리스의 `luna-repro-sdk-0.2.1.zip`을 풀면 `luna-repro-sdk/examples/`가 나옵니다. 그 폴더의 `walkthrough.py`를 설치한 환경의 Python으로 실행하면 로컬 실습이 됩니다. 기본 실행은 네트워크 없이 새 결과 폴더를 만들며 이전 결과를 보존합니다. `--publish`는 별도 선택입니다.

wheel을 먼저 내려받으면 아래 설치는 패키지 색인을 사용하지 않습니다.

```bash
python -m pip install --no-index --no-deps ./luna_repro-0.2.1-py3-none-any.whl
```

ZIP/sdist 설치는 고정 빌드 도구가 필요합니다. 빌드 도구가 없는 오프라인 환경에서는 wheel을 쓰세요. wheel에는 SDK만, 예제 ZIP에는 설치 파일과 예제, 가이드 ZIP에는 한영 문서와 예제가 들어갑니다. `SHA256SUMS`는 릴리스 asset별 SHA256입니다. PowerShell의 `Get-FileHash 파일 -Algorithm SHA256` 또는 `sha256sum 파일`과 대조하세요. 같은 릴리스의 해시 대조는 전송 무결성 확인이며 독립 서명이 아닙니다.

## 문제 해결·버전 경계

- `ModuleNotFoundError`: 예제를 실행하는 Python과 설치한 Python이 같은지 확인합니다.
- 설치 URL 404: 지정한 릴리스 asset이 게시되어 있는지 확인합니다. 다른 이름의 패키지로 자동 대체하지 마세요.
- `pending`: outbox를 보존하고 endpoint·현재 프로젝트 권한·키를 확인한 뒤 명시적으로 재시도합니다.
- Colab 셀 링크: 실제 저장 노트북과 `metadata.id`가 필요합니다. 파일명만으로 정확한 셀 링크를 만들지 않습니다.
- SDK 0.2.1은 플랫폼 0.2.1이라는 뜻이 아닙니다. 전송 계약은 `luna.repro.page.v1`, 선택 출처 확장은 `luna.repro.source.v1`이며 서버가 현재 권한과 한도를 검사합니다.

Git checkout 개발 환경은 `python -m pip install -e .`로 설치한 뒤 `python -m unittest discover -s tests -v`를 실행할 수 있습니다. 개발 체크아웃의 README·예제·가이드도 같은 릴리스 태그를 사용하세요.
