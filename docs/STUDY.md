# 공부 노트

프로젝트를 진행하면서 처음 나온 개념을 순서대로 적는다. 각 항목 끝의 "해보기"는 직접 확인하는 방법이다.

## 1. 전체 그림
- **MLOps**: 모델을 한 번 만들고 끝내지 않고, 새 데이터로 다시 학습하고, 검증하고, 배포하고, 문제가 생기면 되돌리는 과정을 자동으로 돌리는 것.
- **이 프로젝트의 흐름**: 보도자료 수집 → 전처리 → 큰 모델(교사)이 쉬운 말 짝을 만듦 → 작은 모델(학생)을 학습 → 검증(게이트) → GCP에서 카나리·섀도 검증과 승격 → Lightsail champion을 롤링 업데이트, 실패하면 롤백.
- 해보기: `docs/ARCHITECTURE.md`, 보드 https://claude.ai/artifact/Df22Ed1pakpaMb52nr73ei

## 2. 데이터
- **크론(cron)**: 정해진 시각에 명령을 자동으로 실행하는 것. 정부 RSS는 새 글을 알려 주지 않아서(웹훅 없음) 우리가 매일 가져온다.
- **멱등성**: 같은 수집을 여러 번 돌려도 결과가 같은 성질. URL·본문 해시로 이미 받은 글을 건너뛰어서 만든다.
- **결측 처리**: 빈 값을 추측해서 채우지 않고 버리며 이유를 기록한다. 학습 데이터에 지어낸 값이 섞이는 것을 막기 위함.
- **데이터 누수**: 같은 문서의 문장이 학습과 평가 양쪽에 들어가면 성능이 실제보다 좋아 보인다. 그래서 문서 단위로 나눈다.

## 3. 모델
- **교사·학생(지식 증류)**: 큰 모델(gemma3:27b)이 만든 답을 정답으로 삼아 작은 모델(KoBART)을 학습시키는 것. 큰 모델은 서버에 못 올리니 능력을 작은 모델로 옮긴다.
- **파인튜닝**: 이미 한국어를 아는 모델을 우리 작업에 맞게 조금 더 학습시키는 것. KoBART는 작아서 모든 가중치를 학습한다(전체 파인튜닝).
- **LoRA**: 원래 가중치는 그대로 두고 옆에 작은 보조 행렬만 학습하는 방법. 큰 모델을 가볍게 학습할 때 쓴다. 이 프로젝트에서는 KoBART가 기준을 못 넘을 때 Qwen3-0.6B에만 쓴다.
- **ONNX·INT8 양자화**: ONNX는 모델을 여러 실행 환경에서 돌릴 수 있게 저장하는 형식. INT8 양자화는 숫자를 작은 정수로 바꿔 모델 크기와 계산량을 줄이는 것. 메모리 1.9GB 서버에 모델 여러 개를 올리기 위함.

## 4. 검증과 배포
- **게이트**: 새 모델이 지금 모델(champion)보다 나쁘면 배포를 막는 자동 검사. 두 모델 모두 `data/eval/eval_set.jsonl`에서 다시 평가한 지표끼리 비교하고, 평가셋 SHA-1이 다르면 중단한다. SARI와 BERTScore는 검수 정답(`ref`)을 기준으로 계산한다. 원문 대비 BERTScore는 진단용으로만 남긴다. 첫 champion의 `bert_score_ref` 하한 0.75는 임시 기준이며 새 평가 결과를 본 뒤 재검토한다.
- **parity**: 학습할 때의 모델 출력과 서버 컨테이너에서의 출력이 같은지 확인하는 것. 변환·환경 차이로 결과가 달라지는 사고를 막는다.
- **멀티 클라우드 확정 구조**: Route 53 기본 가중치는 Lightsail 90 / GCP 10이고, 헬스체크에 실패한 쪽은 제외한다. Lightsail은 champion만 실행한다. GCP Cloud Run은 API·웹·모델/스토리지의 3티어이며 1GiB, 최소 1·최대 3개 인스턴스로 자동 확장한다.
- **카나리·섀도**: 새 모델 검증은 GCP에서만 한다. 카나리는 Cloud Run 리비전 비율을 나눠 새 버전의 실제 응답을 일부 트래픽에 제공한다. 섀도는 같은 입력으로 새 모델도 실행하되 그 결과는 사용자에게 보내지 않는다. Lightsail에는 카나리·섀도·오토스케일링이 없다.
- **롤링 업데이트**: GCP에서 검증·승격한 champion을 Lightsail의 `api-1`, `api-2`에 하나씩 교체한다. 한 컨테이너가 요청을 계속 처리하는 동안 다른 쪽을 바꾸고, health·smoke 확인이 실패하면 바꾼 컨테이너를 이전 이미지로 되돌린다. 작업 중 Route 53 가중치를 올릴 수 있고 끝나면 90/10으로 복구한다.
- **다단계 이미지 빌드**: Dockerfile의 빌드 단계에서 프론트엔드와 의존성을 준비한 다음, 실행 단계에는 서비스에 필요한 파일만 복사한다. 최종 이미지에서 학습·개발 도구를 빼 크기와 공격 표면을 줄인다. 이 프로젝트에서는 약 509MB에서 427MB로 줄었다.
- 해보기: `docs/ARCHITECTURE.md`, `docs/DEPLOY.md`, `Dockerfile`을 읽고 `deploy/rolling.sh`의 순서를 따라간다.

## 5. 운영
- **장애 조치(failover)**: 주 서버(AWS)가 죽으면 DNS(Route 53)가 요청을 대기 서버(GCP Cloud Run)로 돌리는 것.
- **부하 차단(load shedding)**: 감당할 동시 요청 수를 넘으면 일부를 HTTP 429로 빠르게 거절해 메모리·CPU가 모두 고갈되는 것을 막는다. 부하 테스트는 용량 이내에서 429가 없는지와, 초과 버스트에서 429는 나고 5xx는 없는지를 나눠 확인한다.
- **연쇄 다운**: 같은 원인(예: 새 모델의 버그)이 두 클라우드를 함께 멈추게 하는 것. GCP에서 새 champion을 검증한 다음 Lightsail을 순차 갱신해 영향 범위를 나눈다.

## 6. 업로드 서비스 (T8)
- docx·hwpx는 zip 안에 XML 문서가 들어 있는 형식이라 표준 라이브러리로 글자를 꺼낸다.
- **압축 폭탄**: 작은 zip이 풀면 수 GB가 되도록 만든 파일. 풀린 크기 합계에 상한(20MB)을 둬서 막는다.
- **이벤트 루프 막힘**: FastAPI의 `async` 함수 안에서 무거운 계산을 하면 그동안 다른 요청을 못 받는다. 무거운 작업은 `run_in_threadpool`로 별도 스레드에서 돌린다.
- 해보기: `HOST_PORT=18017 docker compose -p study-upload -f deploy/compose.yaml up -d --build` 후 http://localhost:18017 에서 txt·docx 파일을 올리고, `docker compose -p study-upload -f deploy/compose.yaml down`으로 정리한다.

## 7. 학습·안전장치·협업
- **Early stopping(조기 종료)**: train loss가 계속 낮아져도 valid loss가 나빠지면 과적합 신호다. T6 v1의 무작위 분할 valid loss는 `2.013 → 1.890 → 1.944 → 1.935 → … → 2.129`로 epoch 2에서 최저였다. 그 가중치를 복원하고 2 epoch 연속 개선이 없자 epoch 4에서 멈췄다.
  - 해보기: `sed -n '45,57p' docs/T6_V1.md`로 epoch별 손실을 비교하고, 학습 데이터가 준비되어 있다면 `python -m training.train --version v1 --pairs data/pairs.jsonl --epochs 8`로 다시 학습한다.
- **시간 누수와 데이터 누수**: 무작위 분할의 v1 test에는 train보다 이른 11-07 글이 포함돼 시간 순서를 거슬렀다. 문서 ID·원문·정규화 유사 문장·교사 출력·parity 입력이 train과 valid/test에 겹치는 데이터 누수는 별도로 검사했고 v1에서 모두 0건이었다. T6_V1 표에서 시간순 분할의 최저 valid loss는 1.890에서 2.211로 높아졌다.
  - 해보기: `sed -n '59,87p' docs/T6_V1.md`로 비교·검사 표를 읽고, 데이터가 있으면 `python -m training.train --version v1 --pairs data/pairs.jsonl --split time --docs data/docs.jsonl --check-leakage`를 실행한다.
- **시간순 분할과 독립 평가셋**: 시간순 분할의 valid/test는 통과 학습 짝을 게시 시각으로 나눈 미래 데이터다. 학습이 시간 이후의 문장에 얼마나 일반화되는지 보고 early stopping·게이트에 쓴다. 별도 평가셋은 학습 짝과 분리해 모은 후보를 Claude가 검수해 `src`와 기준 답(`ref`)을 고정한 데이터다. 학습에 넣지 않고, 같은 문항으로 모델 버전 간 품질을 비교한다. 두 데이터 모두 train과 겹치지 않아야 한다. 자세한 한계는 `docs/EVAL_SET.md`에 기록한다.
- **폴백(fallback)은 숫자 안전장치**: `simple_word/numbers.py`가 숫자·날짜·금액·비율을 정규화해 원문과 모델 출력을 비교한다. 값이 달라지면 해당 문장만 원문으로 돌린다. v1 평가 72문장 중 5문장이 폴백되어 `fallback_rate`는 0.0694였고, 숫자 일치율은 1.0이 됐다.
  - 해보기: `.venv/bin/python -m pytest -q tests/test_simplifier.py -k number_guard`와 `rg -n "fallback_rate" docs/T6_V1.md training/evaluate.py`를 실행한다.
- **CI 검사**: `.github/workflows/ci.yml`의 네 job은 Docker 이미지 빌드, 대시보드 테스트·coverage, 프런트엔드 단위 테스트·빌드, Python pytest다. 네 job 모두 통과해야 병합할 수 있다.
  - 해보기: `gh run list --workflow CI --limit 5`로 실행을 찾고 `gh run view <RUN_ID>`로 네 job 결과를 확인한다.
- **Squash 병합 뒤의 충돌**: squash는 PR의 여러 커밋을 새 단일 커밋으로 main에 넣는다. 원래 브랜치의 커밋은 main의 조상으로 기록되지 않으므로, 오래된 브랜치를 다시 main과 합치면 Git이 이미 반영된 패치를 또 적용하려다 충돌할 수 있다. 다음 작업은 최신 main에서 새 브랜치로 시작하고, 이전 브랜치에만 남은 변경이 있으면 그 커밋만 옮긴다.
  - 해보기: `git log --oneline --graph --decorate --all -20`으로 그래프를 확인한 뒤 `git fetch origin && git switch -c codex/new-task origin/main`으로 새 브랜치를 만든다. 미병합 변경만 남았다면 `git cherry-pick <only-unmerged-commit>`을 실행한다.

## 8. 테스트 층
- **단위 테스트**: `pytest`로 숫자 보존, 라우팅, 입력 검증처럼 코드 한 부분을 빠르게 확인한다.
- **통합 테스트**: `scripts/integration.py`가 별도 Compose 프로젝트를 띄워 업로드·피드백·동시 요청 제한·레지스트리 교체를 함께 확인한다.
- **배포 검증**: PR에서는 배포·API·모델·프런트엔드 파일을 바꿀 때 `.github/workflows/deploy-check.yml`이 `deploy/test-local.sh`를 실행한다. 배포 파이프라인은 이 재사용 워크플로를 카나리 전과 Lightsail 롤링 전에 같은 이미지·모델 버전으로 호출한다. 이 검사는 격리된 Compose 프로젝트에서 무중단 롤링·실패 복구와 smoke를 확인한다. nightly나 주간 예약은 두지 않는다.
- **스모크 테스트**: 배포 직후 `scripts/smoke.py <주소>`로 health와 모델 버전, 숫자 보존, 문장 수, fallback 응답을 빠르게 확인한다.
- **부하 테스트**: `scripts/load.py`가 동시 요청의 응답 시간 분포와 429 비율을 출력하고, 기준 옵션이 주어지면 초과 시 실패한다.
- **브라우저 E2E**: Playwright가 실제 브라우저에서 업로드부터 결과 표시까지 화면과 API 연결을 검증한다. `.github/workflows/ci.yml`은 프런트엔드 단위 테스트·빌드를 돌리고, 브라우저 E2E는 `frontend`의 `npm run e2e`로 별도 실행한다. E2E와 backend nightly는 서로 다른 경로를 확인한다.
- **모델 게이트·parity**: 게이트는 새 모델이 champion 기준을 넘는지 확인하고, parity는 학습 때와 서비스 컨테이너의 출력 차이를 확인한다.

## 9. 자리표시자 학습 실험
- **자리표시자(placeholder)**: 학습 입력에서 숫자·날짜·금액과 보존 용어를 임시 표식으로 바꾸고, 모델 출력 뒤 원래 값을 복원하는 방법이다. 모델이 숫자나 법률·기관 명칭을 새로 만들거나 바꾸는 실수를 줄일 수 있다.
- v3에서는 동일한 시간순 분할로 기본 모델(`v3-base`)과 자리표시자를 적용한 모델(`v3-ph`)을 각각 학습·양자화·평가해 비교한다. 실험 결과가 좋아야 후보로 올리며, 자릿값 복원이나 문맥이 깨지면 채택하지 않는다.

## 10. 코드 커버리지
- **라인 커버리지**는 테스트가 실제로 실행한 코드 줄의 비율이다. CI는 `api`, `simple_word`, `gate` Python 패키지와 frontend의 `src/lib`, `src/stores`, `src/api`를 각각 80% 이상으로 요구한다. Python은 `pytest-cov`의 `--cov-fail-under=80`, 프런트엔드는 Vitest v8의 경로별 `lines: 80` 기준을 쓴다.
- 프런트엔드 보고서는 `src/components`와 `src/views`도 포함해 테스트가 닿은 범위를 보여 주지만, 이 화면 전체에는 별도 80% 기준을 두지 않는다. 핵심 데이터 처리 모듈 기준을 유지하면서 화면별 테스트 확대 여지를 보기 위해서다.
- 학습 쪽은 모델 백엔드 없이 시험할 수 있는 `checks`, `preprocess`, `terms`, `eval_set`, `stats`, `pipeline`만 측정한다. `train.py`는 Torch 학습, `export.py`는 ONNX 변환, `teacher.py`는 Ollama 호출을 수행하므로 제외 목록과 이유를 `pyproject.toml`에 둔다. 별도 평가 모듈처럼 모델·네트워크 실행 경로가 필요한 코드는 순수 함수 범위에 넣지 않는다.
- **80%는 품질 보증이 아니다.** 줄이 실행됐다는 뜻일 뿐, 결과가 맞는지·경계값을 확인했는지 보장하지 않는다. 숫자 보존, 오류 응답, 회귀 사례처럼 중요한 동작을 직접 검증하는 테스트와 함께 본다.
- 해보기: 저장소 루트에서 `python -m pytest -q --cov=simple_word --cov-report=term-missing --cov-fail-under=80`, `cd frontend && npm run test:coverage`를 실행한다.
