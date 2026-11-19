# 공부 노트

프로젝트를 진행하면서 처음 나온 개념을 순서대로 적는다. 각 항목 끝의 "해보기"는 직접 확인하는 방법이다.

## 1. 전체 그림
- **MLOps**: 모델을 한 번 만들고 끝내지 않고, 새 데이터로 다시 학습하고, 검증하고, 배포하고, 문제가 생기면 되돌리는 과정을 자동으로 돌리는 것.
- **이 프로젝트의 흐름**: 보도자료 수집 → 전처리 → 큰 모델(교사)이 쉬운 말 짝을 만듦 → 작은 모델(학생)을 학습 → 검증(게이트) → 일부 요청에만 먼저 배포(카나리) → 괜찮으면 전체 배포, 나쁘면 롤백.
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
- **게이트**: 새 모델이 지금 모델(champion)보다 나쁘면 배포를 막는 자동 검사.
- **parity**: 학습할 때의 모델 출력과 서버 컨테이너에서의 출력이 같은지 확인하는 것. 변환·환경 차이로 결과가 달라지는 사고를 막는다.
- **champion·canary·shadow**: champion은 지금 서비스 중인 모델. canary는 새 모델을 일부 요청(예: 10%)에만 먼저 쓰는 것. shadow는 새 모델을 같이 돌리되 결과는 기록만 하고 사용자에게 보여주지 않는 것.
- **레지스트리(`registry.json`)**: 지금 어떤 버전이 champion·canary인지 적은 파일. 배포와 롤백은 이 파일만 바꾼다.

## 5. 운영
- **장애 조치(failover)**: 주 서버(AWS)가 죽으면 DNS(Route 53)가 요청을 대기 서버(GCP Cloud Run)로 돌리는 것.
- **부하 차단**: 감당 못 할 만큼 요청이 몰리면 일부를 429로 거절해서 서버 전체가 죽지 않게 하는 것. Lightsail은 오토스케일링이 없어서 이것으로 버틴다.
- **연쇄 다운**: 같은 원인(예: 새 모델의 버그)이 대기 서버까지 같이 죽이는 것. 그래서 GCP에는 검증이 끝난 champion만 올린다.

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
- **폴백(fallback)은 숫자 안전장치**: `simple_word/numbers.py`가 숫자·날짜·금액·비율을 정규화해 원문과 모델 출력을 비교한다. 값이 달라지면 해당 문장만 원문으로 돌린다. v1 평가 72문장 중 5문장이 폴백되어 `fallback_rate`는 0.0694였고, 숫자 일치율은 1.0이 됐다.
  - 해보기: `.venv/bin/python -m pytest -q tests/test_simplifier.py -k number_guard`와 `rg -n "fallback_rate" docs/T6_V1.md training/evaluate.py`를 실행한다.
- **CI의 세 검사**: `.github/workflows/ci.yml`의 `docker`는 이미지 빌드, `dashboard`는 Node 22에서 대시보드 테스트와 coverage, `test`는 Python 3.11에서 pytest를 실행한다. 세 job 모두 통과해야 병합할 수 있다.
  - 해보기: `gh run list --workflow CI --limit 5`로 실행을 찾고 `gh run view <RUN_ID>`로 세 job 결과를 확인한다.
- **Squash 병합 뒤의 충돌**: squash는 PR의 여러 커밋을 새 단일 커밋으로 main에 넣는다. 원래 브랜치의 커밋은 main의 조상으로 기록되지 않으므로, 오래된 브랜치를 다시 main과 합치면 Git이 이미 반영된 패치를 또 적용하려다 충돌할 수 있다. 다음 작업은 최신 main에서 새 브랜치로 시작하고, 이전 브랜치에만 남은 변경이 있으면 그 커밋만 옮긴다.
  - 해보기: `git log --oneline --graph --decorate --all -20`으로 그래프를 확인한 뒤 `git fetch origin && git switch -c codex/new-task origin/main`으로 새 브랜치를 만든다. 미병합 변경만 남았다면 `git cherry-pick <only-unmerged-commit>`을 실행한다.
