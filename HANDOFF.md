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
- 검증: 프런트 단위 11개, 빌드 통과, E2E 2개, Python 50 passed / 1 skipped. 로컬 v2 모델 파일이 없어 실제 모델 parity 검증은 해당하지 않는다.
