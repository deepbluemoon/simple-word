# Model Gate Report

## v2 vs v3-base

| 지표 | Champion | 후보 |
|---|---:|---:|
| number_date_amount_match_rate | 1.0 | 1.0 |
| preserved_terms_retention_rate | 1.0 | 1.0 |
| bert_score | 0.8348 | 0.8229 |
| sentence_length_reduction_rate | -0.081 | -0.0427 |
| difficult_term_retention_rate | 0.6316 | 0.5263 |
| sari | 0.3932 | 0.3943 |
| cpu_p95_ms_per_sentence | 93.0 | 81.0 |
| model_memory_mb | 271.4 | 269.1 |

**결과: FAIL**

### 이유
- bert_score: 0.8229 is below champion 0.8348

## 지난 버전 이력

| 시각 | Champion | 후보 | 결과 |
|---|---|---|---|
| 2026-11-20T01:47:40.451682+00:00 | v2 | v3-base | FAIL |
