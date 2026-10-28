# 1단계: 게임 엔진 조사 및 실행

조사·실행일: 2026-10-28. 기준: Notion 「05. 개발 로드맵」의 1단계와 「엔진 후보 설치·실행 및 규칙 적합성 조사」.

## 결정

**RiichiEnv 0.4.11을 로컬 엔진 검증용으로 채택**한다. Windows용 사전 빌드 wheel 설치, 4인 한 국 종료, 합법 행동 선택, 플레이어별 정보 은닉 및 동일 시드 재현을 직접 확인했다. Python 3.12를 사용하고 직접·전이 의존성은 `uv.lock`에 고정했다. 최종 제품 규칙, UI, API 서버, 저장소는 미결정이다.

## 후보와 근거

| 후보 | 확인한 역할·요건 | 판단 |
| --- | --- | --- |
| [RiichiEnv 0.4.11](https://pypi.org/project/riichienv/0.4.11/) | Python >=3.10,<3.15, Rust 코어, Windows CPython 3.12 wheel 제공. 상태 진행·합법 행동·점수·MJAI 지원 | 이번 단계에서 설치·실행. 직접 의존성은 PyYAML, IPython, Pygments. wheel 사용으로 Rust 설치 불필요 |
| [mahjong 2.1.0](https://pypi.org/project/mahjong/2.1.0/) | Python >=3.10, 샹텐·화료·점수 계산 | 전체 대국 상태 엔진 대체 용도와 구분. research 그룹에서만 설치해 샹텐 4개 사례 교차 확인 |
| [MahJax](https://github.com/nissymori/mahjax) | JAX 기반 벡터화 시뮬레이터. 공식 pyproject는 Python >=3.9, JAX/FastAPI/uvicorn 등을 명시 | 대량 RL 실험이 현재 목표가 아니므로 보류. 이번 단계에서 설치·성능·Windows 호환성 검증하지 않음 |
| [Mortal](https://github.com/Equim-chan/Mortal) | 학습된 정책과 MJAI 연동 후보 | 게임 규칙 엔진의 대체가 아님. MVP에 학습 모델이 필수이지 않아 도입하지 않음. 가중치·데이터 조건 미검토 |

RiichiEnv 검토 소스는 [v0.4.11](https://github.com/smly/RiichiEnv/tree/v0.4.11), 커밋 `cd450aef2cc3d0dc8654bf81f314c0c82f9c9829`다. 조사 때 PyPI JSON에서 0.4.11과 mahjong 2.1.0이 최신 버전임을 확인했다. MahJax/Mortal은 공식 main 문서만 비교했고 특정 릴리스를 선정하지 않았다.

## 실행 환경과 재현

- Windows x86_64, uv 0.13.6, CPython 3.12.16.
- 초기에는 Python/uv가 PATH에 없었다. 공식 GitHub 배포 zip으로 `.tools/uv.exe`를 준비하고 uv로 Python 설치 후 `.venv`를 생성했다. 사용자 셸 프로필이나 시스템 PATH는 변경하지 않았다.
- 실행 명령은 README에 수록. `.tools`, `.venv`, `.research`, `artifacts`는 Git 제외.
- `python -m mapago_tools.engine_probe --seed 42`는 매번 새 환경으로 두 번 실행한다. JSON 정규화한 **전체 원본 이벤트와 선택 행동**의 SHA-256 및 점수·순위를 비교한다. 원본은 파일에 기록하지 않는다.
- 기존 저장소에 `.gitmodules` 없는 `mapago` gitlink가 있어, 검증 코드는 독립적인 `mapago_tools` 패키지에 둔다. 기존 gitlink는 변경하지 않았다.
- 이는 고정 시드 재실행 검증이다. 저장된 이벤트로 상태를 복원하는 복기/재생 기능은 2단계 이후 작업이다.

| 조건 | 결과 |
| --- | --- |
| tenhou, seed 42, first-legal-v1 | 94 step, 95 행동 결정, 동1국 1회 종료, 유국 |
| 최종 점수, 좌석 0~3 | 24000 / 24000 / 24000 / 28000 |
| 엔진 순위, 좌석 0~3 | 2 / 3 / 4 / 1 (동점 처리 순서를 포함한 엔진 반환값) |
| 이벤트 | start_game 1, start_kyoku 1, tsumo 70, dahai 82, chi 5, pon 7, ryukyoku 1, end_kyoku 1, end_game 1 |
| 재현 해시 | f305f2bc48af537d55ed987477875c0ffc012678f2bbf4c6f44ac55fa5bce023 |
| 자동 테스트 | unittest 8개 통과. 두 프리셋 × seed 0/1/20261028 각각 두 번 비교, seed 42 반복, 다른 시드 해시 차이, 상대 정보 은닉과 누출 거부, 제한 횟수·설정 오류 검사 |
| 보조 계산 | 일반형 완성/텐파이, 칠대자 완성, 국사무쌍 텐파이 4사례가 RiichiEnv와 mahjong에서 각각 -1/0/-1/0으로 일치 |

표본은 동작 확인용이다. 승률·실력·레이팅·전체 규칙 정확성의 근거로 사용하지 않는다. Linux/macOS 실행은 검증하지 않았다.

## 상태·행동 API와 경계

[공식 타입 선언](https://github.com/smly/RiichiEnv/blob/v0.4.11/src/riichienv/_riichienv.pyi), [게임 모드](https://github.com/smly/RiichiEnv/blob/v0.4.11/src/riichienv/game_mode.py)와 설치된 wheel 동작을 함께 확인했다.

1. `RiichiEnv(game_mode=GameType.YON_IKKYOKU, seed=..., rule=...)`로 생성한다.
2. `reset(oya=0, honba=0)`은 현재 결정이 필요한 좌석의 `dict[int, Observation]`을 반환한다.
3. `observation.legal_actions()`의 실제 Action 객체만 선택해 `step({seat: action})`에 전달한다. 응답 단계에는 여러 좌석이 활성화될 수 있다.
4. `done()`, `scores()`, `ranks()`로 종료와 결과를 읽는다. 단계 상한을 두고 빈 관측·빈 합법 행동은 실패 처리한다.
5. `Observation.to_dict()`의 `hands`는 자기 패만 포함하고 상대 패는 빈 배열이다. 관측 이벤트의 상대 초기 패와 쯔모는 `?`다. 전체 실행 중 이를 검사하며, 의도적으로 누출시킨 관측이 거부되는지도 검사했다.

엔진 객체는 모든 손패·패산 및 `mjai_log`를 보유한다. 정책에는 좌석별 Observation만 전달해야 한다. 검사 도구는 원본 로그를 메모리에서만 비교하고 요약에는 엔진/정책 버전, 프리셋, 점수, 이벤트 개수와 해시만 내보낸다. 이는 제품 응답 DTO의 보안 검증을 대신하지 않는다. 미래 API는 허용 필드만 명시적으로 직렬화하고, 시드·패산·상대 원본 관측·전지적 로그를 제외해야 한다.

## 규칙 조사

실험은 `GameRule.default_tenhou()`를 **명시적으로** 사용한다. 이것은 제품 규칙 확정이나 천봉과의 완전한 일치 보증이 아니다. `GameRule()` 생성자와 프리셋 기본값도 구분해야 한다.

[공식 rule.rs](https://github.com/smly/RiichiEnv/blob/v0.4.11/riichienv-core/src/rule.rs)에서 확인한 차이:

| 옵션 | tenhou 프리셋 | mjsoul 프리셋 |
| --- | --- | --- |
| 국사무쌍의 암깡 론 허용 | false | true |
| 국사 13면·사암각 단기·순정구련·대사희 더블 역만 | 각 false | 각 true |
| 역만 책임 지불자만 부담 | false | true |
| 삼가화 유국 | true | false |
| 쿠이카에 금지 | true | true |
| 친 첫 타패를 테다시로 기록 | false | true |

두 프리셋에서 한 국 실행·재현을 검증했다. 옵션별 실제 국면 판정을 모두 독립 검증한 것은 아니다. 리치·론/쯔모·후리텐·깡·책임지불·도중유국·적도라·오라스 종료·점수 세부 판정은 향후 회귀 국면과 외부 정답 대조가 필요하다. 제품의 적도라 수, 쿠이탕, 더블 론/삼가화, 역만 중첩, 종료/동점 규칙을 결정하고 지원 여부를 항목별로 확인해야 한다.

## 라이선스와 자산

- RiichiEnv 코드는 [Apache-2.0](https://github.com/smly/RiichiEnv/blob/v0.4.11/LICENSE). 설치 wheel의 dist-info에서도 LICENSE와 THIRD_PARTY_NOTICES.md 포함을 확인했다.
- [공식 제3자 고지](https://github.com/smly/RiichiEnv/blob/v0.4.11/THIRD_PARTY_NOTICES.md)는 Nyanten 유래 테이블에 MIT, Heroicons에 MIT, 패 그림에 CC BY-SA 4.0을 별도로 명시한다. 코드 라이선스와 자산 라이선스를 동일하게 취급하지 않는다. 이번 구현은 viewer/그림을 호출·복사하거나 배포하지 않는다.
- mahjong은 설치 metadata와 LICENSE.txt에서 MIT를 확인했다. 이번에는 research 전용 보조 도구다.
- MahJax 공식 LICENSE는 Apache-2.0, Mortal 공식 LICENSE는 AGPL-3.0이다. 미도입 프로젝트의 모델·데이터·자산 사용 조건은 승인된 것으로 취급하지 않는다.
- 모델 가중치나 대국 데이터셋은 다운로드·사용하지 않았다. 앱 배포 전에는 실제 포함할 전이 의존성과 UI 번들의 고지 및 재배포 조건을 다시 확인한다.

## 남은 항목과 2단계 입력

- 제품 규칙 명세 및 경계 국면의 정답 대조. 이번 완료 범위는 엔진 조사·로컬 한 국 재현까지다.
- 정책 인터페이스를 Observation + 합법 행동으로 제한하고 4개 봇을 독립적으로 연결.
- 한 국/동풍전/반장전 진행, 안전한 이벤트 저장 형식, 저장된 기록을 통한 상태 재구성 검증.
- 버전·규칙·시드·정책 설정을 서버 내부 재현 메타데이터로 보존하는 방법과 클라이언트 정보 은닉 경계 설계.
