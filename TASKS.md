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

| ID | 작업 | 담당 | 상태 |
|---|---|---|---|
| T1 | 아키텍처·모듈 경계·인터페이스 정의 (`docs/ARCHITECTURE.md`) | 총괄 | done |
| T2 | 데이터 조사 (`docs/DATA_RESEARCH.md`, 브랜치 `max/t2-data-research`) | Claude Max | done |
| T3 | Lightsail 사양 확인 | 총괄 | done |
| T4 | 저장소 골격, 테스트 실행 CI | Codex | done |
| T5 | 수집기(크론)·과거 글 채우기·전처리·교사 짝 생성·자동 검사, 50건 배치로 통과율 측정 | Claude Max | doing |
| T6 | 학생 모델 학습(KoBART 전체 파인튜닝, 미달 시에만 Qwen3-0.6B LoRA), ONNX INT8, 실제 `Simplifier` | Claude Max | doing (준비) |
| T7 | 라우터(champion·canary·shadow, registry 다시 읽기), 부하 차단, 게이트·parity, `reports/` 기록 | Codex | doing |
| T8 | 업로드 웹 화면, Dockerfile·docker compose로 로컬 전체 실행 | Codex | done |
| T9 | RM ops-dashboard 가져오기, 로컬 실행 전용, AWS(SSH Docker)·GCP(Cloud Monitoring) 둘 다 감시 | Codex | done |
| T10 | Lightsail·GCP·Route 53 배포와 장애 조치 | Codex + 사용자(계정·도메인) | todo |
| T11 | 평가셋 200건 사람 검수 | 사용자 | todo |
