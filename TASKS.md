# TASKS

## 역할 (simple-word 전용, agy 제외)

| 에이전트 | 위치 | 맡는 일과 구현 범위 | 브랜치 |
|---|---|---|---|
| 총괄 Claude | 로컬 Mac, Herdr w9:p1 | 아키텍처, 모듈 경계·인터페이스, 작업 배분, 통합·리뷰 | `claude/...` |
| Claude Max | 원격 Mac(Ollama 있음), Herdr w9:p3 | 데이터 조사, 데이터 수집·전처리, Ollama 교사 모델로 짝 데이터 생성, 학습·평가 코드와 실행, 추론 모듈, 업로드 웹 화면 | `max/...` |
| Codex | 로컬 Mac, Herdr w9:p2 | FastAPI 서버(업로드, 파일→텍스트, 카나리·섀도 라우팅), 테스트, GitHub Actions CI/CD, 게이트·parity 검증, Dockerfile·배포·롤백 스크립트 | `codex/...` |

- **Lightsail 서버**(Herdr wA:p1, `/srv/eta`): 2 vCPU, 메모리 1.9GB, 디스크 60GB, GPU 없음. Claude는 없고 GitHub Actions 셀프호스티드 러너(`~/actions-runner`)가 있다. 배포 대상이며, 배포는 CI가 이 러너에서 실행한다.
- Herdr는 ssh 너머의 Claude Max를 에이전트로 인식하지 못한다. 지시는 `herdr pane send-text w9:p3` 후 `send-keys enter`로 보낸다.

## 작업

작업의 기준은 GitHub Issues다(https://github.com/deepbluemoon/simple-word/issues). 아래 표는 요약이고, 규칙은 `docs/BRANCHING.md`.

### 현재 기준
- **기준 시점**: 2026-11-22, `main`은 PR #81까지 반영됐다.
- **모델**: champion은 v2이다. 평가셋 v2(200문장, 정답 2개, SHA-1 `8922190f`, `docs/EVAL_SET.md`)로 게이트를 다시 돌려 v2→v3-base가 PASS했다. v3-base는 **canary 후보(weight 0, `pending_canary`)로만** 등록했고, 클라우드 카나리·섀도 검증 전에는 champion을 바꾸지 않는다. v3-ph는 참고용이다(fallback은 가장 낮지만 어려운 용어 유지율이 높음, 조사 교정 #62).
- **배포**: 도메인과 Route 53은 쓰지 않는다. Lightsail nginx가 API 두 개와 Cloud Run `run.app`으로 90/10 분산하고, API 둘 다 실패하면 Cloud Run으로 보낸다. Lightsail 전체 장애 때는 run.app 주소를 수동 안내한다.
- **데이터**: PR #51에서 두 부처 3,788개 문서, 20,768개 짝, 통과 13,176개까지 2년치 백필했다. 부처 추가는 미진행.

| ID | 작업 | 담당 | 상태 |
|---|---|---|---|
| T1 | 아키텍처·모듈 경계·인터페이스 정의 (`docs/ARCHITECTURE.md`) | 총괄 | done |
| T2 | 데이터 조사 (`docs/DATA_RESEARCH.md`, 브랜치 `max/t2-data-research`) | Claude Max | done |
| T3 | Lightsail 사양 확인 | 총괄 | done |
| T4 | 저장소 골격, 테스트 실행 CI | Codex | done |
| T5 (#1) | 수집기(크론)·과거 글 채우기·전처리·교사 짝 생성·자동 검사, 50건 배치로 통과율 측정 | Claude Max | done (v0.1) |
| T6 (#2) | 학생 모델 v1 학습(KoBART 전체 파인튜닝), ONNX INT8, 실제 `Simplifier` | Claude Max | done (v0.1; v2는 #28) |
| T7 (#3) | 라우터(champion·canary·shadow, registry 다시 읽기), 부하 차단, 게이트·parity, `reports/` 기록 | Codex | done |
| T8 | 업로드 웹 화면, Dockerfile·docker compose로 로컬 전체 실행 | Codex | done |
| T9 (#5) | RM ops-dashboard 가져오기, 로컬 실행 전용, AWS·GCP 감시 + 비용 | codex2 | done |
| T10 (#6) | Lightsail·Cloud Run 배포와 장애 조치 | codex2 + 사용자 | doing (롤링 로컬 검증 완료, Cloud Run 배포됨) |
| T11 (#7) | 검수 평가셋 200건 준비·검수 | Claude Max + 사용자 | done (v1: Claude 검수 193건 → v2: 200건·정답 2개, 적극적 쉬운 말(#69); 사람 검수 아님) |
| T8b (#4) | 서비스 화면 Airtable 팔레트 | codex2 | done |
| T12 (#8) | 셀프호스티드 러너, 수집·누적 학습 워크플로 | 총괄 + 사용자 | waiting user (러너 토큰) |
| T13 (#28) | 긴 짝·여러 줄 제외 후 백필 데이터로 v2 학습, 시간순 평가와 게이트 검증 | Claude Max | done (v2 champion) |
| T14 | 서비스 화면 붙여넣기·비교 강조·이어 읽기·내보내기·오류 복구 개선 | codex2 | done |
| T15 (#44) | 실행 이미지 다단계 빌드·런타임 파일 최소화, 모델 서빙 검증 | codex2 | done |
| T16 (#50) | 어려운 용어 사전 검색 최적화 | Codex | done (부분 문자열 사전 검사) |
| T17 (#51) | 행안부·복지부 과거 보도자료 백필 | Claude Max | done (3,788문서, 통과 짝 13,176) |
| T18 | 자리표시자 포함 v3 모델 학습·INT8 평가·게이트 비교 | Claude Max | done (v3-base 선택, 평가셋 v2 게이트 PASS → canary 후보; champion v2 유지) |
| T19 (#68) | 문서 보기 리뷰 수정·실제 API E2E 확인·nightly 재검증 | Codex | review |
| T20 (#70) | 보안 보강 후속: PDF 격리, 프록시 설정 복구, 오류 응답·피드백 보호 | Codex | done (merged `47f97b9`) |
| T21 (#72) | Lightsail Caddy HTTPS·요청 IP 관리·프록시 보강 | codex2 | doing |
| T22 (#66) | 배포 검증 경로·롤링 복구 검사·모델 버전 smoke | Codex | done (merged `c8c5dc4`) |
| T23 (#73) | GCP 예산·Artifact Registry·모델 버킷·서비스 계정·GitHub WIF·배포 스크립트 | Codex | done (merged to main) |
| T24 (#81) | PDF 업로드 거절, PDF 파서·의존성 제거, 문서와 화면 갱신 | Codex | done (merged to main) |
| T25 | 예시 파일 TXT·DOCX·HWPX 제공, 제목 문장 원문 유지 | Codex | done (PR #82 merged) |
| T26 (#74) | n-best 빔 추론·export parity 수정 | Codex | PR 준비 중 (`codex/nbest-fixes`) |
