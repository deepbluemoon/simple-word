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

## 2026-11-19 Codex T9
- 화면 이슈 #4: 업로드 UI를 흰 바탕·잉크색·시스템 산세리프·알약형 기본 버튼으로 조정하고 모바일 문장 열 재배치와 포커스 표시를 유지했다. 커밋 `1ceaa40` (`Refs #4`).
- RM `ops-dashboard/`를 가져온 뒤 RM 대응 액션·서비스 이름·운영 스크립트·컨테이너 실행 구성을 제거했다. 기존 RM 다크 모니터링 스타일을 유지하면서 AWS SSH Docker 조회, GCP Cloud Run/Monitoring/Logging 조회, 비용 탭을 추가했다.
- 자격 증명이 없으면 클라우드는 `미연결`, 공시 가격 파일(`src/prices.json`) 기반 월 추정은 USD와 기본 환율 1,350 KRW/USD로 표시한다. AWS Cost Explorer와 GCP Billing Export 연결 시 실제 비용 데이터를 표시한다.
- 서버는 `127.0.0.1`에 고정 바인딩한다. 검증: `node --test` 2 passed; `http://127.0.0.1:9760/api/health` 응답 확인, 양쪽 클라우드 미연결 표시 확인.
