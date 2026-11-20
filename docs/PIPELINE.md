# 자동 학습 파이프라인 (이슈 #8)

```bash
python -m training.pipeline --data-only        # 매일: 수집 → 전처리 → 교사 생성 → 검사
python -m training.pipeline                    # 주 1회: 위 + (통과 짝이 직전 학습보다 200건 이상 늘었으면) 학습 → export → evaluate → 게이트 → 후보 등록
python -m training.pipeline --force            # 건수와 상관없이 학습
python -m training.pipeline --min-new-pairs 500
```

| 단계 | 건너뛰는 조건 |
|---|---|
| collect | 오늘 이미 성공 |
| preprocess | `docs.jsonl` sha1이 지난 성공 때와 같음 |
| teacher | `sentences.jsonl` sha1이 같음 (교사 자체도 이미 한 문장은 건너뜀) |
| check | `pairs.jsonl`과 `training/checks.py` sha1이 같음 |
| decide | 열린 run이 있으면 그 버전으로 이어서. 없으면 `통과 짝 − 직전 학습 통과 짝 < N` 이고 `--force`가 아니면 정상 종료(`stopped`) |
| train | `models/<v>/hf/train_metrics.json` 있음 |
| export | `metadata.json`·`encoder.onnx`·`decoder.onnx`·`parity.jsonl` 있음 |
| evaluate | `metadata.json` metrics에 `eval_model` 있음 |
| gate | run에 게이트 결과 있음 |
| register | 게이트 통과면 `models/registry.json`에 canary 후보(weight 0) 기록. 통과·탈락 모두 run을 닫고 `last_train`에 통과 짝 수를 남긴다 |

- 상태: `data/pipeline_state.json` (단계별 입력 지문, 열린 run, `last_train`, `last_failure`). state가 없으면 직전 학습 기준은 지금 champion의 `hf/train_metrics.json` 분할 크기 합(v2 = 2,053).
- 새 버전 이름: `models/` 아래 `v<N>`의 다음 번호. 학습은 v2와 같이 `--split time --docs data/docs.jsonl`, `data/eval/eval_set.jsonl`이 있으면 누수 검사에 쓴다.
- 실패: 그 단계를 `failed`, 뒤는 `not_run`으로 남기고 종료 코드 1. 다시 돌리면 끝난 단계는 건너뛰고 실패한 단계부터.
- 보고서: `reports/pipeline-<날짜>.json` (같은 날 다시 돌리면 덮어씀). 실행 기록은 실행마다 `reports/pipeline_history.jsonl`에 한 줄씩 쌓인다. 게이트 보고서는 기존대로 `reports/MODEL_REPORT.md`·`model_history.jsonl`.
- 후보 등록까지만 한다. 버킷 업로드 → GCP Cloud Run 카나리·섀도 검증 → GCP champion → Lightsail 롤링 교체는 배포 단계가 `registry.json`의 `candidate.status`를 보고 진행한다.

## 스케줄
- 로컬: `deploy/schedule/crontab.example`, `deploy/schedule/com.simpleword.pipeline-{collect,train}.plist` (예시, 설치 안 함).
- GitHub Actions: `.github/workflows/train.yml` — `runs-on: [self-hosted, trainer]`, 저장소 변수 `TRAINER_ENABLED=true`·`TRAINER_HOME`이 있어야 job이 뜬다. push·PR로는 돌지 않는다.

## 실전 실행 기록 (2026-11-20, `--data-only`)

`data/` 복사본(`.tmp/pipe_data`)에서 `python -m training.pipeline --data-only`를 연달아 돌렸다. 공유 `data/`는 v3 분할·NLI 표시·평가셋이 지금의 `pairs.jsonl`을 기준으로 하고 있어서 건드리지 않았다. 코드는 origin/main `655cd05`(#59 되돌림) 기준이다.

| 실행 | collect | preprocess | teacher | check | 걸린 시간 |
|---|---|---|---|---|---|
| 1 | 새 글 15건 | 문서 3,803 / 문장 40,577 | 새 짝 108 (통과 62) | 통과 13,238 / 전체 20,876 | 약 3분 17초 |
| 2 (같은 날) | 건너뜀 | 건너뜀 | 건너뜀 | 건너뜀 | 1초 미만 |
| 3 (검사 지문 수정 뒤) | 건너뜀 | 건너뜀 | 건너뜀 | 다시 돎(지문 형식이 바뀜) | 1초 |
| 4 | 건너뜀 | 건너뜀 | 건너뜀 | 건너뜀 | 1초 미만 |

- **단계 건너뛰기·state:** 입력 지문이 같으면 건너뛰고, `data/pipeline_state.json`에 단계별 `inputs`·`at`·`result`가 남는 것을 확인했다. 검사는 옛 짝 20,768개의 판정을 하나도 바꾸지 않았다(통과 증가 62 = 새 짝의 통과 수).
- **고친 문제 1. 교사 단계에 문장 제한이 없었다.**
  - `teacher.run(data_dir)`을 그대로 불러서, 짝이 없는 옛 문장 19,530개를 파일 순서대로 모두 교사에게 보냈다. gemma3:27b로는 며칠이 걸린다. 처음 실행은 이 문제로 멈췄다.
  - 지금까지 데이터를 모은 방식(`.tmp/teacher_loop.sh`: `--per-doc 8 --recent-first`)과 같게 `TEACHER_PER_DOC = 8`, 최근 문서부터로 고쳤다. 이번 실행의 교사 대상은 108문장이었다.
- **고친 문제 2. 검사 단계의 규칙 지문이 `training/checks.py`만 봤다.**
  - 판정은 `simple_word/numbers.py`(서빙과 같은 숫자 비교)·`simple_word/terms.py`·`preserve_terms.txt`·`data/nikl_terms.csv`에도 달려 있다.
  - #59와 그 되돌림(#67)은 `numbers.py`만 바꿨다. 그래서 옛 지문으로는 재검사가 돌지 않아 옛 통과 표시가 남는다.
  - 이 파일들을 모두 지문에 넣었다(`check_rules_fingerprint`).
- **고친 문제 3. 같은 날 다시 돌리면 실행 기록이 사라졌다.**
  - `reports/pipeline-<날짜>.json`은 덮어쓰기라, 건너뛰기만 한 2번째 실행이 실제로 일한 1번째 실행의 보고서를 지웠다.
  - 파일은 그대로 두고, 실행마다 `reports/pipeline_history.jsonl`에 한 줄씩 남긴다(traceback 제외).
- **그대로 둔 동작:** 수집 지문이 날짜라서, 같은 날 나중에 올라온 글은 다음 날 수집된다(문서에 적힌 "하루 한 번" 설계).
