# Model Gate Report

## v2 vs v3-base

| 지표 | Champion | 후보 |
|---|---:|---:|
| number_date_amount_match_rate | 1.0 | 1.0 |
| preserved_terms_retention_rate | 1.0 | 1.0 |
| bert_score | 0.8431 | 0.826 |
| sentence_length_reduction_rate | -0.0226 | -0.0015 |
| difficult_term_retention_rate | 0.8 | 0.6667 |
| sari | 0.5389 | 0.5892 |
| cpu_p95_ms_per_sentence | 88.6 | 88.6 |
| model_memory_mb | 267.5 | 267.1 |

**결과: FAIL**

### 이유
- bert_score: 0.826 is below champion 0.8431

## 지난 버전 이력

| 시각 | Champion | 후보 | 결과 |
|---|---|---|---|
| 2026-11-20T01:47:41.108772+00:00 | v2 | v3-base | FAIL |
