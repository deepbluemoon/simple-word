# Model Gate Report

## v2 vs v3-ph

Evaluation set SHA-1: `e3455f4b5dafa67754c2415009bc595fa282d6c2`
- candidate: `e3455f4b5dafa67754c2415009bc595fa282d6c2`
- champion: `e3455f4b5dafa67754c2415009bc595fa282d6c2`

| 지표 | Champion | 후보 |
|---|---:|---:|
| number_date_amount_match_rate | 1.0 | 1.0 |
| preserved_terms_retention_rate | 1.0 | 1.0 |
| bert_score_ref | 0.8276 | 0.8127 |
| sentence_length_reduction_rate | -0.081 | -0.0522 |
| difficult_term_retention_rate | 0.6316 | 0.6842 |
| sari | 0.3932 | 0.3835 |
| cpu_p95_ms_per_sentence | 92.8 | 82.8 |
| model_memory_mb | 271.6 | 269.8 |

**결과: FAIL**

### 이유
- bert_score_ref: 0.8127 is below champion 0.8276
- difficult_term_retention_rate: 0.6842 is above champion 0.6316
- sari: 0.3835 must be above champion 0.3932

## 지난 버전 이력

| 시각 | Champion | 후보 | 결과 |
|---|---|---|---|
| 2026-11-20T02:20:05.120422+00:00 | v2 | v3-ph | FAIL |
