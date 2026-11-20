# Model Gate Report

## v2 vs v3-base

Evaluation set SHA-1: `e3455f4b5dafa67754c2415009bc595fa282d6c2`
- candidate: `e3455f4b5dafa67754c2415009bc595fa282d6c2`
- champion: `e3455f4b5dafa67754c2415009bc595fa282d6c2`

| 지표 | Champion | 후보 |
|---|---:|---:|
| number_date_amount_match_rate | 1.0 | 1.0 |
| preserved_terms_retention_rate | 1.0 | 1.0 |
| bert_score_ref | 0.8276 | 0.8202 |
| sentence_length_reduction_rate | -0.081 | -0.0427 |
| difficult_term_retention_rate | 0.6316 | 0.5263 |
| sari | 0.3932 | 0.3943 |
| cpu_p95_ms_per_sentence | 92.9 | 83.8 |
| model_memory_mb | 271.5 | 269.3 |

**결과: FAIL**

### 이유
- bert_score_ref: 0.8202 is below champion 0.8276

## 지난 버전 이력

| 시각 | Champion | 후보 | 결과 |
|---|---|---|---|
| 2026-11-20T02:18:43.614005+00:00 | dummy | v2 | PASS |
| 2026-11-20T02:19:24.481197+00:00 | v2 | v3-base | FAIL |
