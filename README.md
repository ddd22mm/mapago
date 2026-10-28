# 마파고

일본식 4인 리치 마작 AI 대국 및 코치 시스템. 현재 **2단계: 4개 봇 자동 대국과 기록 저장·재생**까지 구현했습니다.

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

1단계 도구는 엔진 실행 확인용이며, AI 실력이나 코치 추천을 구현한 것은 아닙니다. 원본 로그에는 비공개 패가 있어 메모리에서만 비교하고 출력에는 점수·이벤트 수·검증 해시만 포함합니다.

## 4개 봇 대국과 재생

```powershell
uv run --locked python -m mapago_tools.match run --mode east --seed 42 --output artifacts/match-001.internal.json
uv run --locked python -m mapago_tools.match replay artifacts/match-001.internal.json
uv run --locked python -m mapago_tools.match replay artifacts/match-001.internal.json --viewer 0 --output artifacts/match-001.seat0.json
```

기본값은 독립적인 랜덤 합법 행동 봇 4개와 tenhou 규칙 프리셋입니다. `--mode kyoku|east|hanchan`, `--rule tenhou|mjsoul`, `--dealer 0..3`으로 설정합니다. `--bots first-legal,random-legal,first-legal,random-legal`처럼 좌석별 정책을 지정할 수 있습니다. 이 정책들은 연동 검증용이며 실력이 측정된 AI가 아닙니다.

재생은 봇을 다시 실행하지 않고 **파일에 저장한 행동**을 엔진의 합법 행동 목록과 대조해 적용합니다. 각 단계의 상태·이벤트, 최종 점수·순위까지 검증하며 불일치·손상·버전 차이는 실패 처리합니다. 기존 파일을 덮어쓰지 않으므로 재실행 시 다른 출력 이름을 지정하세요.

`*.internal.json`에는 재현용 시드와 행동 기록이 있어 외부 공개하면 안 됩니다. 해당 파일과 `artifacts/`는 Git에서 제외됩니다. `--viewer` 출력은 선택 좌석의 손패·합법 행동과, 상대 손패·쯔모를 가린 이벤트를 포함한 JSON 복기 프레임입니다. 브라우저 복기 화면은 후속 단계에서 연결합니다.

## 결과와 다음 단계

- [1단계 조사 기록](docs/stage-1-engine-review.md): 후보 비교, 설치, API, 규칙, 라이선스와 미해결 항목
- [실행 결과](docs/validation/engine-probe.json): Windows 로컬 검증 요약
- [2단계 구현 기록](docs/stage-2-auto-match.md): 봇 경계, 내부 저장 형식, 좌석별 재생과 검증
- [자동 대국 결과](docs/validation/stage2-match.json): 동풍전 실행·재생 요약
- [Notion 로드맵](https://app.notion.com/p/4050404e4333811d9b8ee796be12a02f): 개발 범위 기준

다음은 3단계 사용자 대국 UI입니다. UI·API 기술, 운영 저장소·보존 정책과 최종 제품 규칙은 아직 확정하지 않았습니다.
