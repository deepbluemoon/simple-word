# HANDOFF

## 2026-11-18 총괄
- 아이디어 확정: 공문서·안내문 파일을 올리면 쉬운 말로 바꿔 주는 웹 서비스.
- 과정 필수 요구사항: Lightsail 인스턴스·버킷, GitHub CI/CD, 새 데이터 자동 학습과 게이트·parity 검증, API 서버 배포, 롤백. 여기에 카나리·섀도 배포를 추가한다.
- 역할 분배는 `TASKS.md` 참고. agy는 사용량 한도로 약 11/25까지 쓸 수 없어서 Claude Max가 조사와 프론트엔드를 맡는다.
- 가장 큰 미확인 위험: 학습용 짝 데이터와 재학습 루프용 새 데이터를 어디서 얻는가 (T2).

## 2026-11-18 Codex T4
- `codex/t4-skeleton`에서 FastAPI 골격, 결정적 더미 `Simplifier`, TXT 업로드 `/simplify`, `/health`, 테스트와 ubuntu-latest CI를 추가했다.
- 남은 작업: 로컬 pytest 실행은 환경의 mise Python 버전 문제와 시스템 Python의 pytest 미설치로 실행하지 못했다. 의존성 설치는 하지 않았다.

## 2026-11-19 Codex T8
- `codex/t8-web-ui`에서 모바일 대응 업로드 UI, TXT/DOCX/HWPX/PDF 추출, 5 MiB·빈 파일 검증, JSONL 피드백 저장, Dockerfile과 Compose를 추가했다.
- 검증: `pytest -q` 9 passed. Compose 기동 후 `/health`, 샘플 TXT·DOCX 업로드 응답을 확인하고 `down`했다.
- 리뷰 후 압축 해제 총량 20 MiB, PDF 50페이지, 문장 500개 제한과 `/feedback` 문자열 2,000자 제한을 추가했다. 추출·모델 실행은 Starlette threadpool에서 처리한다.
- 검증: `pytest -q` 15 passed. Compose 컨테이너 UID 10001(app) 확인, POST `/feedback` 성공 및 JSONL 저장 확인 후 전용 테스트 볼륨을 제거했다.

## 2026-11-19 Codex T7
- `codex/t7-router-gate`에 registry 기반 champion/canary/shadow 라우터, 비동기 threadpool 추론·요청 부하 제한, PII 가림 요청 JSONL, parity/metric gate와 모델 리포트 생성을 추가했다.
- parity 행 스키마는 `{"input": "문장" 또는 ["문장"], "output": "결과" 또는 ["결과"]}`. 지표 키와 수치는 `gate/thresholds.json` 기준으로 metadata `metrics`에 맞춘다.
- 검증: pytest 23 passed. Compose에서 파일을 바꿔 `hot-a`→`hot-b`가 컨테이너 재시작 없이 `/health`와 `/simplify`에 반영됨을 확인했다.
- 리뷰 #3: 명시된 `dummy` 외 registry 버전은 metadata/ONNX 파일과 모델 로딩을 확인하고 실패 시 경고하며 기존 라우팅을 유지한다. 추론 실패는 role/version/error를 요청 로그에 남기고 500을 반환한다. 메인 슬롯은 추론 직후 반환하고 shadow는 별도 1슬롯 semaphore에서 바쁘면 생략 로그를 남긴다. pytest 27 passed.

## 2026-11-19 Codex T9
- 화면 이슈 #4: 업로드 UI를 흰 바탕·잉크색·시스템 산세리프·알약형 기본 버튼으로 조정하고 모바일 문장 열 재배치와 포커스 표시를 유지했다. 커밋 `1ceaa40` (`Refs #4`).
- RM `ops-dashboard/`를 가져온 뒤 RM 대응 액션·서비스 이름·운영 스크립트·컨테이너 실행 구성을 제거했다. 기존 RM 다크 모니터링 스타일을 유지하면서 AWS SSH Docker 조회, GCP Cloud Run/Monitoring/Logging 조회, 비용 탭을 추가했다.
- 자격 증명이 없으면 클라우드는 `미연결`, 공시 가격 파일(`src/prices.json`) 기반 월 추정은 USD와 기본 환율 1,350 KRW/USD로 표시한다. AWS Cost Explorer와 GCP Billing Export 연결 시 실제 비용 데이터를 표시한다.
- 서버는 `127.0.0.1`에 고정 바인딩한다. 검증: `node --test` 2 passed; `http://127.0.0.1:9760/api/health` 응답 확인, 양쪽 클라우드 미연결 표시 확인.

## 2026-11-19 1차 v0.1 완료·2차 진행
- 1차 기준은 `main`의 `33fe9b6` (`Port ops dashboard to Simple Word`, PR #27)이다. v0.1 범위의 수집·학습 v1·API·게이트·업로드·운영 대시보드가 main에 들어갔다.
- v1은 숫자 안전장치로 `fallback_rate=0.0694`와 숫자 일치율 1.0을 기록했지만 길이 감소율 게이트는 통과하지 못해 champion으로 승격하지 않았다. 상세 표는 `docs/T6_V1.md`를 참고한다.
- 2차 #28은 Claude Max가 백필 통과 짝 2,916건에서 원문보다 1.3배 넘게 긴 짝과 여러 줄 출력을 제외한 뒤 약 2,000건 이상으로 v2를 학습한다. early stopping·누수 검사·시간순 평가를 하고 게이트 통과 전에는 champion을 바꾸지 않는다.
- #6은 codex2가 우선 로컬 배포를 검증한 다음 Lightsail·GCP·Route 53 배포를 진행한다. 실제 클라우드 검증에는 계정·도메인·버킷 준비가 필요하다.
- #7의 200건 사람 검수 평가셋과 #8의 Claude Max 러너 토큰·자동 학습 준비는 사용자 입력을 기다린다.

## 서비스 프론트엔드 개선
- `codex/frontend-polish`: 붙여넣기 입력, 비교 화면의 변경 단어·숫자 표시와 스크롤 동기화, 폴백 사유, 글자 크기 저장·쉬운 말 이어 읽기·복사/내려받기, 429 재시도 상태를 추가했다.
- API는 문단 경계를 보존하고 문장별 폴백 사유와 문단 번호를 반환한다. `simplify_detailed()` 기존 계약은 유지한다.
- 검증: 프런트 단위 11개, 빌드 통과, E2E 2개, Python 53 passed / 1 skipped. 로컬 v2 모델 파일이 없어 실제 모델 parity 검증은 해당하지 않는다.

## 실행 이미지 축소
- `codex/slim-image`: Dockerfile을 다단계로 나눠 Python 의존성만 venv에 설치하고, 최종 단계에는 venv·`api/`·`simple_word/`·`frontend/dist`만 복사한다. training·gate 소스, 테스트·캐시, pip·setuptools 및 dist-info의 설치 기록 파일은 최종 이미지에서 제외한다. UID 10001과 Compose healthcheck는 유지한다.
- `docker history` 비교: 전체 508.9 MB → 426.9 MB(-82.0 MB, -16.1%); 이전 `pip install` 층 224 MB → 새 venv 복사 층 161 MB. `python:3.11-slim`은 유지했다. Alpine은 musl로 ONNX Runtime의 glibc 기반 Linux wheel과 호환 위험이 있고, distroless는 현재 프로젝트의 Python 3.11 런타임 ABI·경로 변경을 수반한다. CPU onnxruntime은 서빙 필수, NumPy는 `simple_word/model.py`의 실제 텐서 입력에 사용한다.
- 검증: Python 53 passed / 1 skipped, `/health`·`scripts/smoke.py` 통과, ONNX Runtime·NumPy·tokenizers import, UID 10001, Compose health healthy. `training/`·`gate/`는 서비스 import 경로에 없고 최종 컨테이너에도 없다. 로컬 ONNX 모델 파일이 없어 parity 20/20은 실행하지 않았다.

## 2026-11-19 Claude Max #8 준비
- `max/8-pipeline`: `training/pipeline.py`(단계 건너뛰기·N건 기준·실패 기록·`reports/pipeline-<날짜>.json`), `gate/registry.py`(`register_candidate`: canary 후보 weight 0), 크론·launchd 예시(`deploy/schedule/`), `.github/workflows/train.yml` 초안, `tests/test_pipeline.py`. 설명은 `docs/PIPELINE.md`.
- 지금 데이터 기준 통과 짝 2,053 = v2 학습 크기 → 새 짝이 200건 늘기 전에는 학습하지 않는다.
- 남은 것: 러너 등록(label `trainer`)과 저장소 변수 `TRAINER_ENABLED`·`TRAINER_HOME` (사용자).

## 2026-11-20 기준 상태 (main, PR #51까지 기능 반영)
- 최신 main에는 PR #51의 2년치 백필 결과가 반영되어 있다: 보도자료 3,788건, 교사 짝 20,768건, 자동 검사 통과 13,176건. 출처는 행정안전부·보건복지부이며 부처 추가는 아직 안 했다. PR #52는 이 진행 기록을 반영한 문서 변경이다.
- Max가 v3 학습 중이다. 같은 시간순 분할에서 `v3-base`와 숫자·보존 용어 자리표시자 `v3-ph`를 각각 학습하고 INT8 평가·게이트 결과를 비교한다. 현재 v3-base epoch 1 valid loss 1.38, v2 최저 1.61. 게이트를 통과한 후보가 나오기 전에는 champion을 변경하지 않는다.
- PR #50의 `found()` 최적화는 사전 1,627개 용어 × 합성 문장 10,000개에서 결과 2,157건 일치, 최적화 후 1.398초였다. 기존 방식 100문장 측정 37.473초를 선형 환산하면 약 62.5분(추정)이다.
- 배포 확정안: Route 53 기본 Lightsail 90 / GCP 10, 장애 위치는 헬스체크로 제외. Lightsail은 champion만 두 컨테이너로 롤링하고, GCP Cloud Run에서만 리비전 비율 카나리·섀도·오토스케일링을 한다. Route 53 실제 가중치 훅은 클라우드 계정·레코드 준비 후 연결한다.
- 다음 남은 일: v3 학습·평가 결과 반영, runner 토큰 준비 후 자동 학습 연결, 클라우드 계정·도메인 준비 후 실배포와 장애 훈련. 평가셋은 Claude가 193건을 검수했으며 사람의 재검토는 별도 결정 사항이다.

## PR #68 문서 보기 리뷰 수정 (Codex)
- 문장 선택 요소를 줄바꿈 가능한 inline 키보드 버튼으로 바꾸고, 의견 투표를 결과·문장 단위로 양쪽 보기와 새로고침에서 공유한다. 활성 보기만 렌더링하며 결과 ID 변경 시 선택과 탭을 초기화한다.
- 폴백 문장의 화면·내려받기·피드백 출력을 원문으로 통일하고, API의 중복 `paragraph` 필드를 제거해 `paragraph_id`만 반환한다.
- 핵심 업로드 E2E와 CSP 진행 표시 확인은 실제 API를 호출하고 실제 응답 문장·문단을 검사한다. 429 테스트만 가짜 응답을 사용한다.
- 검증: API 30 passed, 프론트 단위 17 passed, 타입 검사·색상 검사·프로덕션 빌드 통과. 첫 E2E 실행에서 API 문장 분할 기대값이 잘못된 점을 고친 뒤 nightly run `44673712918`의 browser-e2e·rate-limit·integration 전체 통과. PR #68은 병합 전 총괄 리뷰 대기.

## 2026-11-20 Claude Max 평가셋 v2·재판정
- **평가셋 v2:** `data/eval/eval_set.jsonl`은 200문장, 문장마다 정답 2개(`references`), SHA-1 `8922190f`이다. v1은 `eval_set.v1.jsonl`(`e3455f4b`)에 남겼다. 규칙·예시·재생성 명령(`training.eval_set fill-v2`·`build-v2`)은 `docs/EVAL_SET.md`에 있다. 사람 검수가 아니라 Claude 검수다.
- **게이트(평가셋 v2):** dummy→v2 PASS, v2→v3-base PASS(SARI 0.4870 > 0.4794, bert_score_ref 0.8366 ≥ 0.8346, 어려운 용어 0.50 ≤ 0.60, p95 82.6ms, 메모리 267.6MB).
- **v3-base 등록:** canary 후보(weight 0, `pending_canary`)로만 등록했다(로컬 `.worktrees/v3/models/registry.json`). **champion은 v2 그대로**이고, 클라우드 registry 반영과 카나리·섀도 검증은 배포 단계에서 한다.
- **메모리 주의:** 모델 메모리가 상한 300MB에 가깝다(v2 269.8MB, 다른 작업과 동시에 재면 287MB). 게이트를 돌릴 때는 교사 LLM 같은 무거운 작업을 멈춘다.
- **지연 측정:** 별도 프로세스에서 잰다(BERTScore·champion 평가가 끼지 않게, #69 후속).
- **#59 되돌림(#67):** 그 사이(12:49~) main으로 잰 fallback·숫자 일치 값은 버리고 `655cd05` 기준으로 다시 쟀다.
