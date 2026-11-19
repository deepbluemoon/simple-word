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
- 보고서: `reports/pipeline-<날짜>.json` (같은 날 다시 돌리면 덮어씀). 게이트 보고서는 기존대로 `reports/MODEL_REPORT.md`·`model_history.jsonl`.
- 후보 등록까지만 한다. 버킷 업로드 → GCP Cloud Run 카나리·섀도 검증 → GCP champion → Lightsail 롤링 교체는 배포 단계가 `registry.json`의 `candidate.status`를 보고 진행한다.

## 스케줄
- 로컬: `deploy/schedule/crontab.example`, `deploy/schedule/com.simpleword.pipeline-{collect,train}.plist` (예시, 설치 안 함).
- GitHub Actions: `.github/workflows/train.yml` — `runs-on: [self-hosted, trainer]`, 저장소 변수 `TRAINER_ENABLED=true`·`TRAINER_HOME`이 있어야 job이 뜬다. push·PR로는 돌지 않는다.
