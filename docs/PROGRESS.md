# simple-word 진행 기록

공문서·안내문 파일을 올리면 쉬운 말로 바꿔 주는 웹 서비스. 일어난 순서대로 적고, 새 단계는 맨 아래에 붙인다.
담당: 총괄(로컬 Claude), Codex·codex2(구현·리뷰·테스트·CI·배포 스크립트), Claude Max(조사·데이터·학습·프론트엔드).

---

# 1차 (v0.1)

## 1. 기획
- 아이디어 확정: 공문서 → 쉬운 말 변환, 파일 업로드 방식.
- 과정 필수 요구사항: Lightsail 인스턴스·버킷, GitHub CI/CD, 새 데이터 자동 학습 + 게이트·parity 검증, API 서버 배포, 롤백. 여기에 카나리·섀도 배포를 더하기로 함.
- 가장 큰 위험으로 "학습용 짝 데이터를 어디서 얻나"를 꼽음.

## 2. 데이터 조사 (T2, Max) — `docs/DATA_RESEARCH.md`
- 학습 머신: Max Mac(M5 Ultra, 96GB 통합 메모리, Ollama). 27B급 교사 모델도 로컬로 돌릴 수 있음.
- 배포 대상 Lightsail(2 vCPU, 2GB, GPU 없음) → 학생 모델은 1B 이하·양자화가 필요.
- 짝 데이터 후보와 지속 공급원(정부 RSS)을 실제로 호출해 확인.
- **증류** 방식 결정: 큰 교사 모델(gemma3:27b)이 쉬운 말 짝을 만들고, 작은 학생 모델(KoBART)이 그것을 배운다.

## 3. API 골격 (T4, Codex)
- FastAPI, 결정적 더미 `Simplifier`, `/simplify`·`/health`, 테스트, GitHub Actions CI.

## 4. 아키텍처 — `docs/ARCHITECTURE.md`
- AWS Lightsail이 주 서버, GCP Cloud Run이 대기 서버. Route 53 헬스체크가 실패하면 DNS를 GCP로 돌림(장애 조치). (2차 33번에서 확정안으로 바뀜)
- 학습은 Max Mac의 셀프호스티드 러너. 운영 대시보드는 서비스 서버 밖(사용자 Mac)에서.
- Lightsail에는 오토스케일링이 없으므로 업로드·문장 수 상한과 동시 처리 제한, 넘치면 429로 거절(부하 차단).

## 5. 업로드 화면과 로컬 컨테이너 (T8, Codex)
- TXT·DOCX·HWPX·PDF 글자 추출, 5MB·빈 파일 검사, 피드백(JSONL) 저장, Dockerfile·Compose.
- 리뷰 후 보강: 압축 해제 총량 20MB(압축 폭탄 방지), PDF 50쪽, 무거운 처리는 threadpool로(이벤트 루프 막힘 방지).
- 학습 노트(`docs/STUDY.md`) 시작.

## 6. 협업 규칙
- 이슈·PR 템플릿, 브랜치 규칙(`docs/BRANCHING.md`) (#9).
- CI를 PR마다 한 번만 실행 (#12).
- 모든 작업은 `simple-word` 안에서. worktree·임시 파일도 그 아래 (#13).

## 7. 운영 화면과 대시보드 (T8b·T9, Codex) — PR #15
- 업로드 화면을 흰 바탕·잉크색·알약형 버튼으로 다듬음.
- RM `ops-dashboard`를 가져와 AWS(SSH Docker 조회)·GCP(Cloud Monitoring·Logging)·비용 탭을 붙임. 자격 증명이 없으면 "미연결"과 공시 가격 기반 추정으로 표시.

## 8. 라우터·게이트 (T7, Codex) — PR #14
- `registry.json` 기반 champion / canary / shadow 라우터. 파일만 바꾸면 컨테이너를 재시작하지 않아도 모델이 바뀜.
- 동시 처리 제한, 개인정보를 가린 요청 로그, parity·지표 게이트, 모델 리포트.
- 리뷰 후: 모델 파일이 깨졌으면 경고하고 기존 라우팅 유지, shadow는 별도 1슬롯에서 바쁘면 생략.

## 9. 데이터 파이프라인 (T5, Max) — PR #10, `docs/T5_RESULTS.md`
- 수집(RSS) → 전처리(담당자·첨부 줄 제거, 개인정보 가림, 길이·한글 비율·중복 필터) → 교사 짝 생성(gemma3:27b) → 자동 검사.
- 첫 실행: 문서 50건 → 문장 988 → 통과 짝 885(89.6%).

## 10. 학생 모델 드라이런 (T6, Max) — PR #11, `docs/T6_DRYRUN.md`
- KoBART 파인튜닝 → ONNX 변환 → INT8 양자화 → 모델 폴더 164.6MB(기준 300MB 이하).
- parity 20/20 일치. 품질은 보지 않고 처음부터 끝까지 도는지만 확인.

## 11. 테스트·운영 보강 (Codex)
- Docker 빌드 수정과 대시보드 검사를 CI에 추가 (#19). CI 검사가 `test`·`docker`·`dashboard` 3개가 됨.
- 업로드 문장 수 상한을 100으로 낮춤 (#20).

## 12. 첫 champion 게이트 기준 (#21, Codex) — PR #24
- 원문 대비 BERTScore는 "원문 그대로"가 항상 1.0이라 더미를 이길 수 없음 → 첫 champion은 고정 하한(BERTScore ≥ 0.75, 길이 감소율 ≥ -0.10)으로 검사.

## 13. v1 학습과 학습 검증 (T14, Max) — PR #25, `docs/T6_V1.md`
- 885짝, 문서 단위 분할. epoch 2 이후 과적합 → **early stopping**으로 epoch 2 가중치 복원.
- **시간 누수**: 무작위 분할 test에 학습보다 이른 글이 섞임 → 시간순 분할로도 다시 잼.
- **데이터 누수**: 같은 문서·문장·유사 중복·parity 입력 겹침 0건. 겹치면 학습을 거부.
- 긴 입력(255토큰 초과)은 자르지 않고 원문 반환. 게이트 지표는 INT8 ONNX로만 계산.

## 14. 숫자 안전장치 (T18, Max) — PR #26
- 출력의 숫자·날짜·금액·비율이 원문과 다르면 그 문장만 원문을 돌려주고 `fallback`으로 기록.
- v1 숫자 일치 0.93 → 1.0, fallback 6.9%. 그래도 길이 감소율 -0.166으로 게이트 불통과 → champion은 더미 유지.

## 15. 운영 대시보드 이식 (T17, Codex) — PR #27
- RM ops-dashboard 기능 전체를 디자인을 유지한 채 simple-word용으로 이식.

## 16. 1차 마감
- 태그 `v0.1` (main `33fe9b6`). 수집·학습 v1·API·게이트·업로드·운영 대시보드가 로컬에서 끝까지 동작.

---

# 2차

## 17. 문서 정리 (Codex) — PR #29
- STUDY.md 7장(early stopping, 시간·데이터 누수, 폴백, CI 3개 검사, squash 병합 뒤 충돌). TASKS·HANDOFF를 1차 기준으로 갱신.

## 18. 확인 두 가지 (총괄)
- 대시보드 비용표의 Lightsail 2GB 22 USD는 Windows 가격. Linux 공인 IPv4는 12 USD.
- 호스트 8000번은 아무도 쓰지 않음. 8000은 컨테이너 안의 포트이고, 호스트 18016이 거기로 연결됨.

## 19. 가격·포트 수정 (Codex) — PR #30
- 비용표 22 → 12 USD(출처 링크 포함), `scripts/load.py` 기본 포트를 18016으로.

## 20. v2 학습 → 첫 champion (#28, Max) — PR #31, `docs/T6_V2.md`
- 교사 검사에 길이 규칙 추가: 원문 대비 1.3배 초과(848)·여러 줄(44) 제외 → 2,916 → 2,053짝.
- 시간순 분할 train 1,706 / valid 161 / test 186, 누수 0건, early stopping으로 epoch 2 복원.
- 첫 게이트 불통과: 보존 용어 0.972 → **보존 용어 안전장치** 추가(빠지면 그 문장 원문 반환).
- 최종: 길이 -0.035, BERTScore 0.837, 숫자·보존 용어 1.0, fallback 10.2%, parity 20/20 → **게이트 통과, champion = v2**.

## 21. 테스트 격리 (Codex) — PR #32
- `tests/test_api.py`가 로컬 `models/registry.json`을 읽어 실패하던 문제 → 임시 경로를 쓰게 고침.

## 22. 로컬 배포·롤백·카나리 스크립트 (#6 일부, codex2) — PR #33, `docs/DEPLOY.md`
- `deploy.sh`(헬스체크 실패 시 직전 태그로 자동 복구), `rollback.sh`, `canary.sh`(nginx 비율 분배 → 승격·철회), `test-local.sh` 검증.
- 카나리가 두 층: **이미지 카나리**(새 코드)와 **모델 카나리**(`registry.json`). (35번에서 Lightsail 카나리는 제거)

## 23. 3티어 구조안 (총괄)
- https://claude.ai/artifact/HvabuUKpFbPKsvUz9cWy5z (기존 아키텍처 그림 페이지는 그대로). A 주-대기 / B 화면 분리 + DB / C 가중치 둘 다 받기 비교.

## 24. 서비스 웹 UI (Max) — PR #35
- 끌어다 놓기, 처리 중 표시, 한국어 오류, 2단 비교, "원문 유지" 배지, 복사·내려받기. `/simplify` 응답 문장에 `fallback` 추가.

## 25. GHCR 이미지 빌드 (#6 일부, codex2) — PR #34
- main push와 `v*` 태그마다 이미지를 `ghcr.io/deepbluemoon/simple-word`에 올림(태그 `sha-xxxx`, `main`, 버전).

## 26. CI 밖 테스트 보강 (Codex) — PR #36
- `scripts/smoke.py`: 배포 직후 health·숫자 보존·fallback 키 확인, 실패하면 롤백.
- `nightly.yml`: 매일 통합·배포 검증·부하 테스트. STUDY.md에 테스트 층 정리.

## 27. nightly 부하 기준 수정 (Codex) — PR #37
- 동시 10개 → 429 66.7%로 실패했지만 서비스 고장이 아니라 기준이 설계와 안 맞았음.
- 두 단계: 용량 이내(동시 2) 429 0%·p95 통과 / 용량 초과 버스트 429 발생·5xx 0 통과.
- 개념: **부하 차단(load shedding)**.

## 28. RM 서비스 프론트엔드 이식 (codex2) — PR #38
- RM `frontend/`(Vue 3 + Vite + TypeScript)를 가져와 디자인은 유지하고 서비스 연결과 문구만 교체. 옛 `web/` 삭제.
- 남긴 화면: 공문서 올리기, 진행 표시, 원문/쉬운 말 비교, 원문 유지 배지, 의견, 최근 결과, 모델 서버 상태, API 안내. 로그인·관리자 화면은 뺌.
- CI 검사 4개: test·docker·dashboard·**frontend**.

## 29. 클라우드별 컨테이너 대시보드 (Codex) — PR #39
- AWS: 호스트 → 컨테이너(역할), GCP: Cloud Run 서비스 → 리비전(트래픽 %) → 인스턴스 수·CPU·메모리, 로컬 Docker도 같은 모양.

## 30. 평가셋 후보 준비 (#7, Max) — PR #40
- 학습·parity와 겹치지 않는 문장에서 200건 층화 추출, 검수 CSV, 고친 CSV → eval_set.jsonl, 누수 검사 연결.

## 31. v2 배포 크기 측정 (Max) — PR #41
- 로컬 프로세스 기준: 유휴 약 355MiB, 최대 약 370MiB, 1문장 p95 85ms, 시작 1초 이내.
- 판단: Cloud Run 1GiB, Lightsail 2GB는 api 2개 + proxy도 여유(추정).

## 32. 재부팅 복구
- 에이전트 세션이 새로 열림. codex2 프론트 작업은 커밋 전 상태로 남아 있어 이어서 진행. Docker 재시작 후 로컬 서비스·대시보드 다시 띄움.

## 33. 아키텍처 확정 (사용자 결정)
- Route 53 가중치 Lightsail 90 / GCP 10, 헬스체크로 죽은 쪽 제외.
- Lightsail 2GB: champion만, nginx 뒤 api 컨테이너 2개 부하분산, 새 champion은 롤링 업데이트.
- GCP Cloud Run(3티어): 카나리(리비전 비율)·섀도·오토스케일링(1GiB, min 1, max 3). Lightsail 장애 시 100% 받음.
- 새 champion 순서: 학습·게이트 → GCP 섀도·카나리 → GCP champion → (GCP 비율 잠깐 올림) Lightsail 롤링 교체 → 10% 복귀.
- EC2는 쓰지 않음(과정 요구사항이 Lightsail, 같은 사양에서 EC2가 더 비쌈).
- 클라우드 연결: VPN 없이 두 클라우드 독립, 연결은 CI·학습 머신·대시보드에서 HTTPS와 권한 나뉜 키로만.

## 34. 서비스 프론트 개선 (codex2) — PR #42
- 붙여넣기 입력, 바뀐 단어·숫자 보존 강조, 원문 유지 이유, 글자 크기·이어 읽기, 내보내기, 429 재시도, 접근성.

## 35. Lightsail 롤링 업데이트 (Codex) — PR #43
- compose: api-1, api-2 + nginx 부하분산(한쪽 실패 시 재시도). Lightsail 카나리 제거.
- `rolling.sh`: GCP 가중치 훅 → api-1 교체·smoke → api-2 교체·smoke → 복귀, 실패 시 직전 태그로.

## 36. 이미지 줄이기 (codex2) — PR #44
- 다단계 빌드로 실행에 필요한 것만. 509MB → **427MB**(-16%). training/·gate/ 제외.

## 37. 학습 파이프라인 (#8 준비, Max) — PR #45
- `python -m training.pipeline`: 수집→…→게이트, 이미 한 단계 건너뜀, 통과 짝 200건 이상 늘었을 때만 학습, 통과하면 canary 후보 등록. 크론 예시, 러너용 `train.yml`.

## 38. 어려운 용어 사전 넓히기 (codex2) — PR #46, `docs/DIFFICULT_TERMS.md`
- 국립국어원 평가용 용어 + **법제처 법령용어-일상용어** 사전을 출처 표시와 함께 합침. 라이선스 불명확·변경 금지 출처는 제외.
- 교사 프롬프트, 자동 짝 검사, 평가셋 분류, 어려운 용어 잔존 지표가 같은 사전을 씀.

## 39. 평가셋 Claude 검수 (#7, Max) — PR #47, `docs/EVAL_SET.md`
- 후보 200건 중 193건 검수(사람 검수 아님을 명시).
- v2를 이 평가셋으로 재니 test 분할보다 낮음: SARI 0.539 → **0.393**, 길이 -0.035 → **-0.081**, fallback 10% → **19%**, 어려운 용어 잔존 **0.63**(19개).

## 40. 진행 기록 git 관리 — PR #48
- git 제외 로컬 파일이던 PROGRESS.md가 에이전트의 `git clean`으로 지워짐 → PR·결과 문서로 복구하고 커밋 로그와 PR 번호 대조(빠진 것 없음) → 저장소에 넣음.

## 41. 장기 작업 분리 (Max)
- 사용자 노트북이 잠들면 SSH가 끊겨 원격 수집·교사 생성까지 죽을 수 있어서, 두 작업을 SSH와 분리(`nohup`·`setsid`, 부모 1)하고 원격에 `caffeinate`.

## 42. 어려운 용어 적용 범위 측정 (Max)
- 통과 짝 원문 중 국립국어원 목록 용어가 든 문장은 **1.6%**(보도자료에는 외래어 위주인 이 목록의 말이 드묾). 법제처 사전은 Open API 인증값(OC)이 없어 아직 못 받음.
- 측정 한 번에 약 20분 → Codex가 용어 검사 속도 개선 중(`codex/fast-term-match`).

## 43. 용어 검사 속도 개선 (Codex) — PR #50
- `found()`가 정규식을 만들기 전에 단순 문자열 포함으로 먼저 거름. 1만 문장 × 1,627 용어: 약 62분(추정) → **1.4초**, 결과 동일.

## 44. 2년치 백필 (Max) — PR #51, `docs/T5_RESULTS.md`
- 문서 150 → **3,788**(행안부 2024~26, 복지부 2025~26), 짝 20,768, 통과 **13,176**(v2 학습 때 2,053의 약 6.4배). 부처 추가는 아직 안 함.
- 짝마다 교사 프롬프트 판 기록, 기간·부처별 통계, data.go.kr 보도자료 수집기(키 있을 때만).

## 45. v3 학습 (Max) — PR #54, `docs/T6_V3.md`
- 통과 13,176짝, 시간순 분할(train 8,384 / valid 1,721 / test 3,071)로 v3-base(기존)·v3-ph(자리표시자) 비교. 학습 전 audit·누수 0건, 둘 다 epoch 2 복원.
- 평가셋 193: v3-base SARI 0.394(v2 0.393), 길이 -0.043(v2 -0.081), 어려운 용어 0.53(v2 0.63), fallback 18.7%(v2 19.2%), p95 81ms. BERTScore(원문 대비)만 0.823 < v2 0.835 → **게이트 FAIL**, champion은 v2 유지.
- v3-ph: fallback 13.5%로 가장 낮지만 되돌릴 때 조사 오류("건강보험를").

## 46. E2E 테스트를 nightly에 (codex2) — PR #55
- Playwright로 업로드·붙여넣기 → 결과 → 의견 → 새로고침, 오류 상태까지 매일 브라우저로 확인.

## 47. 게이트 기준 변경 결정 (사용자)
- 원문 대비 BERTScore는 쉽게 바꿀수록 떨어져 변환을 벌점 주는 구조 → **평가셋 검수 정답 대비**로 바꾸고, 두 모델을 같은 평가셋으로 다시 재서 비교. 결과를 본 뒤 바꿨으므로 v2·v3 모두 새 기준으로 재판정.
- SARI가 낮은 이유: 정답 1개, 어절 단위 비교(조사 차이 감점), 원문 그대로도 약 0.40 → 원문·교사 기준선과 형태소 단위 SARI를 함께 기록.

## 48. 진행 중
- **codex2**: [C] n-best 안전 후보 선택 구현 완료(이 PR). `decoding.num_beams` 기본 1, 안전 검사 통과 후보 선택, parity 재생성·p95/RSS 비교 도구 추가. 로컬 80 passed, 1 skipped; 모델이 없어 실측은 Max Mac에서 필요. 다음은 사용자가 지정한 21st.dev 참고 기반 프론트 디자인 통일 작업.
- **Codex**: 보안 보강 → [A] 숫자를 (기준어, 값) 짝으로 개수까지 비교 → CI 커버리지 80% 기준.
- **Max**: [D] 자리표시자 조사 교정 + v3-ph 재평가 → [B] 학습 짝 뜻 검사(NLI) → 게이트 병합 후 v2·v3 재판정.
- 보류: 서빙 때 뜻 검사(B'), 절 단위 부분 fallback(E) — 위 결과를 보고 결정.
- 배포 검증을 PR 경로 조건부 + 주 1회로 바꿀지: 사용자 답 대기.

## 47. 게이트 참조 기준 변경 (Codex)
- `training/evaluate.py`에서 SARI와 `bert_score_ref`를 검수 정답 기준으로 계산하고, 원문 대비 BERTScore는 `bert_score_source` 진단값으로 보존. 원문 그대로와 교사 출력의 SARI·BERTScore 및 공백·조사 분리 근사 SARI도 기록.
- 게이트가 champion과 후보를 동일 평가셋으로 재평가하고 SHA-1을 비교·보고하도록 변경. 이전 `bert_score` 메타데이터 키는 제거하며, 임계값 0.75는 유지하고 재검토 TODO를 문서화.
- v2·v3 새 기준 재판정은 Max Mac에서 수행 예정. 명령: `python -m gate.gate v2 v3-base --models-dir models --reports-dir reports/gate-eval-reference --data-dir data`.

## 49. 프론트 디자인 통일 (Codex)
- 21st.dev의 12개 UI 패턴을 기존 Vue 화면에 반영하고, 재사용 코드는 가져오지 않음. 출처와 라이선스 확인 여부는 `docs/FRONTEND_REFERENCES.md`에 기록.
- 색 토큰을 잉크·회색·성공·주의·오류 역할로 정리하고, 빌드에서 토큰 밖의 CSS 색상값을 차단. 비교 강조는 회색 바탕+밑줄, 상태는 문구와 점으로 함께 표시.
- 최근 결과의 상대 시간, 바뀐 문장 수, 의견 확인 안내, 상태 라벨 및 4단계 진행 표시를 정리. 서버가 문장별 실시간 진행을 주지 않아 가짜 퍼센트 대신 indeterminate 상태를 사용.
- 검증: 프론트 단위 테스트 13개와 프로덕션 빌드 통과. Playwright는 사용자 지침에 따라 로컬 스크린샷이 생기는 실행을 하지 않음.

## 50. 문서 보기와 nightly E2E 정리 (Codex)
- 결과 기본 화면을 문서 보기로 바꾸고, 바뀐 말만 옅은 노랑으로 표시. 문장 선택 시 원문·원문 유지 사유·의견을 옆 메모에 표시하고 좁은 화면에서는 아래에 배치. 기존 문장별 비교는 탭으로 유지.
- 문단별 복사·내려받기를 유지하도록 API에 `paragraph`를 추가하고 기존 `paragraph_id`도 함께 보존. 오래된 저장 결과의 `paragraph_id`만 사용하던 데이터도 계속 읽음.
- nightly의 진행률 접근성 이름을 실제 UI와 맞추고 CSP 위반 검사는 유지. 중복 Playwright job을 캐시·실패 아티팩트가 있는 단일 job으로 합침.
- 검증: API 30개, 프론트 단위 17개, 타입·색상 검사·빌드 통과. 로컬 Playwright는 스크린샷 금지 지침으로 실행하지 않고 nightly 수동 실행을 통해 검증 예정.

## 사용자 준비 (필요해질 때)
- 클라우드: GCP 프로젝트·결제(`gcloud auth login`), 도메인(Route 53), Lightsail 2GB 인스턴스·버킷
- #8 자동 학습: Max Mac `gh auth login`, 러너 토큰
- 데이터 확대(선택): data.go.kr 보도자료 OpenAPI serviceKey 발급, AI Hub 행정문서 데이터 신청
