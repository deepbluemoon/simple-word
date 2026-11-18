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
| T1 | 아키텍처·모듈 경계·인터페이스 정의 (`docs/ARCHITECTURE.md`) | 총괄 | review |
| T2 | 데이터 조사: 짝 데이터, 재학습용 새 데이터 공급원, Ollama 교사 모델 실험 | Claude Max | doing |
| T3 | Lightsail 사양 확인 | 총괄 | done |
| T4 | 저장소 골격, 테스트 실행 CI 기본 구성 | Codex | review |
