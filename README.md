# 마파고

일본식 4인 리치 마작 AI 대국 및 코치 시스템. 기본 실행 환경은 Docker Compose입니다. **3단계 사용자 대국 화면과 엔진 연결**을 구현했습니다. API 검증을 마쳤으며 실제 브라우저 화면·조작 확인은 남아 있습니다.

## 사용자 대국 화면

```powershell
docker compose up --build -d
```

Docker Desktop을 실행한 뒤 저장소 폴더에서 실행합니다. 처음 설치했으면 PATH 반영을 위해 기존 터미널을 닫고 새 터미널을 여세요. 브라우저에서 **http://127.0.0.1:8765**를 열고 「대국 시작」을 누르세요. 종료는 `docker compose down`, 로그 확인은 `docker compose logs -f`입니다. 포트 8765가 사용 중이면 PowerShell에서 `$env:MAPAGO_PORT=8766`으로 바꾸고 접속 주소도 `http://127.0.0.1:8766`로 사용하세요.

최초 사용에는 Docker Desktop, WSL 2, BIOS/UEFI에서 켠 하드웨어 가상화가 필요합니다. Docker 엔진이 시작하지 않으면 작업 관리자 > 성능 > CPU의 「가상화」 상태를 확인하세요. Compose는 서비스 포트를 호스트 `127.0.0.1`에만 공개하므로 LAN에서는 접속할 수 없습니다.

대국 화면 실행에는 위의 Docker Compose 명령을 사용하세요. Python/uv 직접 실행은 엔진 분석과 개발 보조용입니다.

- 나는 동가·친으로 시작하고 세 명의 봇과 동1국을 진행합니다.
- 손패를 선택한 뒤 「타패」를 누릅니다. 가능한 순간에 치·퐁·깡·리치·론·쯔모·패스 등의 행동이 표시됩니다.
- `←` / `→`로 패 선택, `D`로 타패, `Esc`로 패스할 수 있습니다.
- 한 국 종료 후 점수 변화와 결과를 확인하고 「내 기록 저장」으로 내 좌석의 JSON 복기를 내려받습니다.
- 새로고침하면 같은 브라우저 세션의 대국을 불러옵니다. 서버를 재시작하면 메모리의 대국은 사라집니다.

현재는 로컬 전용 프로토타입이며 외부 네트워크 배포는 지원하지 않습니다. 화면의 상대는 연동 검증용 봇이고 코칭·실력별 난이도는 후속 단계입니다.

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

기본값은 독립적인 랜덤 합법 행동 봇 4개와 tenhou 규칙 프리셋입니다. `--mode kyoku|east|hanchan`, `--rule tenhou|mjsoul`, `--dealer 0..3`으로 설정합니다. `--bots rule-based,random-legal,first-legal,random-legal`처럼 좌석별 정책을 지정할 수 있습니다. `rule-based-v1`은 엔진의 샹텐 계산과 공개 정보 기반 유효패 휴리스틱으로 타패를 고르는 초기 정책이며, 호출은 보수적으로 패스합니다. 성능이나 레이팅은 측정된 바 없습니다.

재생은 봇을 다시 실행하지 않고 **파일에 저장한 행동**을 엔진의 합법 행동 목록과 대조해 적용합니다. 각 단계의 상태·이벤트, 최종 점수·순위까지 검증하며 불일치·손상·버전 차이는 실패 처리합니다. 기존 파일을 덮어쓰지 않으므로 재실행 시 다른 출력 이름을 지정하세요.

`*.internal.json`에는 재현용 시드와 행동 기록이 있어 외부 공개하면 안 됩니다. 해당 파일과 `artifacts/`는 Git에서 제외됩니다. `--viewer` 출력은 선택 좌석의 손패·합법 행동과, 상대 손패·쯔모를 가린 이벤트를 포함한 JSON 복기 프레임입니다. 브라우저 복기 화면은 후속 단계에서 연결합니다.

## 학습형 AI 검토 후보

- [cai_Akagi의 4인 Mortal](https://github.com/caizizhen/cai_Akagi/tree/main/mjai_bot/mortal)을 후속 검토 후보로 기록합니다. 현재 채택하거나 설치한 의존성은 아닙니다.
- Git LFS 포인터 기준 모델 크기는 130,797,985바이트(약 131MB)이며, 원본 경로의 16바이트 범위 요청만 확인했습니다. 전체 가중치 다운로드·추론·성능 검증은 하지 않았습니다.
- PyTorch 기반 ResNet·DQN과 MJAI JSONL 입출력 구조를 제공합니다. 연결 시 `mjai_bot/common/policy_guard.py` 의존성, 좌석별 정보 필터링, RiichiEnv 합법 행동과의 대조를 검토해야 합니다.
- README의 작성(雀聖) 수준·학습량 설명은 제작자 주장입니다. Mortal 하위 폴더의 AGPL-3.0과 가중치 이용 조건, 학습 데이터 출처는 도입 전에 확인해야 합니다.
- [상세 조사 기록(Notion)](https://app.notion.com/p/4080404e433381d8bc38ccaa347bd243)

## 결과와 다음 단계

- [1단계 조사 기록](docs/stage-1-engine-review.md): 후보 비교, 설치, API, 규칙, 라이선스와 미해결 항목
- [실행 결과](docs/validation/engine-probe.json): Windows 로컬 검증 요약
- [2단계 구현 기록](docs/stage-2-auto-match.md): 봇 경계, 내부 저장 형식, 좌석별 재생과 검증
- [자동 대국 결과](docs/validation/stage2-match.json): 동풍전 실행·재생 요약
- [3단계 구현 기록](docs/stage-3-human-ui.md): 화면·API·세션·검증 결과와 브라우저 확인 제한
- [Notion 로드맵](https://app.notion.com/p/4050404e4333811d9b8ee796be12a02f): 개발 범위 기준

다음 확인 항목은 실제 브라우저에서 한 국 조작과 화면 배치 검증입니다. 이후 4단계 샹텐·유효패 기반 정책을 구현합니다. 운영 기술·저장소·보존 정책과 최종 제품 규칙은 아직 확정하지 않았습니다.
