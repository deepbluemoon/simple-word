# Model Gate Report

## v2 vs v3-base

Evaluation set SHA-1: `8922190fee493df3f292f4a49294dd7e97a25dd6`
- candidate: `8922190fee493df3f292f4a49294dd7e97a25dd6`
- champion: `8922190fee493df3f292f4a49294dd7e97a25dd6`

| 지표 | Champion | 후보 |
|---|---:|---:|
| number_date_amount_match_rate | 1.0 | 1.0 |
| preserved_terms_retention_rate | 1.0 | 1.0 |
| bert_score_ref | 0.8346 | 0.8366 |
| sentence_length_reduction_rate | -0.0809 | -0.0421 |
| difficult_term_retention_rate | 0.6 | 0.5 |
| sari | 0.4794 | 0.487 |
| cpu_p95_ms_per_sentence | 91.7 | 82.6 |
| model_memory_mb | 269.9 | 267.6 |

**결과: PASS**

## 지난 버전 이력

| 시각 | Champion | 후보 | 결과 |
|---|---|---|---|
| 2026-11-20T04:20:44.248589+00:00 | dummy | v2 | PASS |
| 2026-11-20T04:21:25.124180+00:00 | v2 | v3-base | PASS |
