# 마파고

일본식 4인 리치 마작 AI 대국 및 코치 시스템. 현재는 개발 1단계인 **게임 엔진 조사·실행·한 국 재현**을 완료했습니다.

## 실행

Python 3.12와 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 사용합니다. uv는 필요한 Python을 자동으로 설치합니다.

```powershell
uv sync --locked
uv run --locked python -m mapago_tools.engine_probe --seed 42 --output artifacts/engine-probe.json
uv run --locked python -m unittest discover -s tests -v
```

이 PC에는 uv를 프로젝트 내부 `.tools/uv.exe`에 설치했습니다. PATH에 uv가 없으면 위 명령의 `uv` 대신 `.\.tools\uv.exe`를 사용하세요.

검증 도구는 RiichiEnv 0.4.11의 4인 한 국 모드에서 첫 번째 합법 행동을 선택합니다. 동일 시드로 두 번 실행해 모든 행동·이벤트의 해시와 결과가 일치하는지 검사합니다. 실패하면 종료 코드 1을 반환합니다. `--rule mjsoul`로 다른 엔진 프리셋도 실험할 수 있습니다.

보조 라이브러리의 샹텐 계산 비교:

```powershell
uv run --locked --group research python -m mapago_tools.analysis_probe
```

이 정책은 엔진 실행 확인용이며, AI 실력이나 코치 추천을 구현한 것은 아닙니다. 원본 로그에는 비공개 패가 있어 메모리에서만 비교하고 출력에는 점수·이벤트 수·검증 해시만 포함합니다. 시드는 실험 재현용으로만 사용하며 실제 대국 클라이언트에 공개하면 안 됩니다.

## 결과와 다음 단계

- [1단계 조사 기록](docs/stage-1-engine-review.md): 후보 비교, 설치, API, 규칙, 라이선스와 미해결 항목
- [실행 결과](docs/validation/engine-probe.json): Windows 로컬 검증 요약
- [Notion 로드맵](https://app.notion.com/p/4050404e4333811d9b8ee796be12a02f): 개발 범위 기준

다음은 2단계인 4개 봇 연결, 자동 대국 및 이벤트 저장·재생입니다. UI·API·저장소 기술과 제품 규칙은 아직 확정하지 않았습니다.
