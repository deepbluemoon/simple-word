# 아키텍처

그림: https://claude.ai/artifact/Df22Ed1pakpaMb52nr73ei (드래그로 수정 가능, 로컬 스냅샷은 git에서 제외된 `.board/`)

## 클라우드 구성

| 구역 | 구성 |
|---|---|
| 진입 | Route 53 가중치 라우팅 기본값은 Lightsail 90 / GCP 10. 양쪽 헬스체크를 연결하고 죽은 위치는 라우팅에서 제외한다. 장애 조치 시 살아 있는 쪽이 100%를 받는다. |
| AWS (champion) | Lightsail(2 vCPU·2GB): HTTPS nginx가 동일 이미지·모델의 `api-1`, `api-2`로 부하분산한다. champion만 실행하며 카나리·섀도·오토스케일링은 두지 않는다. Lightsail 버킷: `models/`, `data/`, `registry.json`, `logs/`. |
| GCP (검증 및 champion) | Cloud Run 3티어, 1 GiB, 최소 1·최대 3 인스턴스. 리비전 비율 카나리, 섀도 트래픽, 오토스케일링을 사용한다. 비밀값은 Secret Manager. |
| 학습 | Claude Max Mac(GitHub 셀프호스티드 러너 `trainer`): 수집·전처리·교사 생성·학습·평가. |
| 모니터링 | RM `ops-dashboard`를 가져와 **서비스 서버 밖(사용자 Mac, 127.0.0.1)** 에서 실행. AWS는 SSH를 통한 Docker 조회, GCP는 Cloud Monitoring·Logging API를 조회 전용 계정으로 읽는다. 서비스 서버가 털려도 감시 도구와 그 자격 증명은 함께 털리지 않게 하기 위함. |

장애 조치 시간은 헬스체크와 DNS 캐시 영향이 있으므로 실제 장애 훈련으로 잰다.

- **확장**: Lightsail에는 오토스케일링이 없다. 대신 업로드 크기·압축 해제 크기·문장 수 상한, 동시 처리 수 제한과 넘치면 429로 거절(부하 차단)을 둔다. 파일 입력은 TXT·DOCX·HWPX를 지원하고 PDF는 처리하지 않는다. 더 커져야 하면 스냅샷으로 큰 플랜에 옮긴다(수직 확장). Cloud Run은 자동 확장하되 최대 대수를 정한다.
- **GCP 용량**: Cloud Run은 최소 1대·최대 3대로 autoscale한다. 기본 Route 53 가중치는 Lightsail 90 / GCP 10이며, Lightsail 교체 동안 가중치를 임시 상향할 수 있다.
- **champion 승격**: 새 모델은 GCP 카나리 리비전 비율과 섀도 트래픽으로 검증한 뒤 GCP champion이 된다. 이후 Lightsail의 두 API 컨테이너를 하나씩 헬스·smoke 확인하며 갱신하고 가중치를 기본값으로 되돌린다.
- **장애 분리**: Route 53 헬스체크가 장애 위치를 라우팅에서 제외한다. 웹 화면 재시도는 간격을 점점 늘린다.

## 데이터 파이프라인 (Claude Max Mac)

- **수집**: 크론(매일). 웹훅이 아닌 이유는 정부 RSS가 새 글을 알려 주지 않는 pull 방식이기 때문. URL·본문 해시로 이미 받은 글은 건너뛴다(여러 번 돌려도 결과 같음). 과거 글은 부처 보도자료 게시판을 거슬러 올라가며 한 번 채운다.
- **변환 단계**
  1. `raw/<날짜>/<id>.html` 원문 그대로
  2. `docs.jsonl` `{id, url, source, published_at, title, body, fetched_at, license}`
  3. `sentences.jsonl` `{doc_id, idx, text}`
  4. `pairs.jsonl` `{src, tgt, teacher, checks, passed, reject_reason}`
  5. `data/v<N>/` train·valid·test(문서 단위 분할) + 사람 검수 평가셋 200건(고정)
- **전처리 기준**: HTML·메뉴·첨부 목록·담당자 블록 제거, NFC 정규화, 개인정보(전화·이메일·주민번호 형식) 가림, 문장 길이 10~200자, 한글 비율 50% 미만 문장 제외(문장 안의 영어 단어는 남김), 정확·유사 중복 제거.
- **결측 처리**: 채워 넣지 않고 버리며 이유를 기록. 본문 없음 → 문서 버림. 게시일 없음 → 수집 시각으로 대신하고 표시. 교사 출력 없음·실패 → 짝 버림. 버린 비율은 매일 기록하고 급증하면 알린다.
- **짝 검사**: 숫자·날짜·금액·비율 일치(100분의 20 = 20%), 보존 용어(법적 지위·고유명사·공식 명칭) 유지, 대상·기한·조건 누락 여부, 원문의 영어 단어가 결과에 남았거나 사전 대체어로 바뀌었는지.
- **학습 시점**: 매일이 아니라 검사를 통과한 새 짝이 일정량(초기값 2,000건, 첫 수집량 보고 조정) 쌓이거나 드리프트가 감지될 때.

## 모델

- 교사: Ollama `gemma3:27b` (Claude Max Mac, API 비용 없음)
- 학생: KoBART 전체 파인튜닝(시퀀스 단위 지식 증류). KoBART가 게이트 기준을 못 넘을 때만 Qwen3-0.6B LoRA를 시도한다.
- 비교 기준선: 규칙 기반 용어 치환, gemma3:4b.
- 서빙: ONNX INT8, 결정적 디코딩.

## 평가와 게이트

| 구분 | 지표 | 통과 기준 |
|---|---|---|
| 뜻 보존 | 숫자·날짜·금액 일치율, 보존 용어 유지율 | 평가셋 200건에서 100% |
| 뜻 보존 | 원문 대비 의미 유사도(BERTScore) | champion 이상 (첫 champion: 0.75 이상) |
| 쉬움 | 어려운 용어 잔존율(국립국어원 목록), 문장 길이 감소율 | champion보다 나쁘지 않음 (첫 champion: 감소율 -0.10 이상) |
| 정답 비교 | SARI(교사 출력·평가셋 기준) | champion보다 높음 |
| 운영 | 서버 CPU p95 지연, 모델 메모리 | 문장당 1초 이하, 모델당 300MB 이하 (초기값) |
| parity | 학습 환경 출력 = 서빙 컨테이너 출력 | `parity.jsonl` 100% 일치 |

GCP 카나리(리비전 비율)와 섀도 요청으로 새 champion을 검증한다. 실제 요청 기반 품질 지표는 숫자 보존율·용어 잔존율·오류율·지연시간·좋아요 비율을 champion과 비교하며, 하루 한 번 교사 모델로 로그를 다시 채점한다. LLM 채점은 참고 지표이고 게이트 기준이 아니다. Lightsail에서는 카나리나 섀도 트래픽을 보내지 않는다.

## 기록과 알림

- 학습 이력: `reports/model_history.jsonl`(학습 1회 = 1줄)과 여기서 만든 `reports/MODEL_REPORT.md`(champion vs 새 모델). 학습 워크플로가 저장소에 커밋한다.
- 알림: GitHub 기본 메일(워크플로 실패). Lightsail 알람도 메일.
- 데이터베이스는 처음에 두지 않는다. 요청 로그·피드백은 JSONL로 쌓아 몇 분마다 버킷(`logs/`)에 올린다. 복잡한 조회가 필요해지면 PostgreSQL을 추가한다.

## 모듈과 담당

| 경로 | 내용 | 담당 |
|---|---|---|
| `simple_word/model.py` | 추론 인터페이스 | Claude Max |
| `training/` | 수집·전처리·교사 생성·학습·평가 | Claude Max |
| `api/` | FastAPI, 파일→텍스트, 라우터 | Codex |
| `web/` | 업로드 화면 (정적 HTML/JS, api가 서빙) | Codex (Claude Max가 T5 중이라 넘김) |
| `gate/` | 게이트·parity 검증 | Codex |
| `deploy/` | Dockerfile, compose, 배포·롤백 스크립트 | Codex |
| `ops-dashboard/` | RM에서 가져온 운영 대시보드 (로컬 실행) | Codex |
| `.github/workflows/` | CI/CD | Codex |

## 약속

1. **추론**: `Simplifier(artifact_dir).simplify(sentences: list[str]) -> list[str]`. 길이·순서 같음, 같은 입력엔 같은 출력.
2. **모델 아티팩트**: `models/<version>/` = 모델 파일 + `metadata.json`(`version`, `created_at`, `data_snapshot`, `base_model`, `metrics`) + `parity.jsonl`.
3. **레지스트리**: 버킷의 `registry.json` `{"champion": "v3", "canary": "v4", "canary_weight": 0.1, "shadow": null}`. 배포·롤백 = 이 파일 변경.
4. **API**: `POST /simplify`(파일) → `{"model_version", "sentences": [{"original", "simple"}]}`, `POST /feedback`, `GET /health`.
5. **서빙 컨테이너**: 모델 폴더는 읽기 전용(`:ro`)으로 마운트. 쓰기는 로그 폴더만.
6. **로컬 먼저**: 서버에 올리기 전에 `docker compose up`으로 로컬에서 같은 구성을 띄워 확인한다.
