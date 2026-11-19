# T6 드라이런: KoBART 학생 모델 파이프라인 (품질 아님)

작성: Claude Max (브랜치 `max/t6-student-model`), 2026-11-19. 목적은 **처음부터 끝까지 도는지**와 크기·속도 확인. 품질 평가는 하지 않았다.

## 실행한 것

```
python -m training.train  --version v0-dryrun --pairs <T5 pairs.jsonl 스냅숏> <T2 gemma3:27b 3건> --epochs 2
python -m training.export --version v0-dryrun
```

| 단계 | 결과 |
|---|---|
| 데이터 | T5 교사 생성 도중 스냅숏 302짝 중 passed 275 + T2 gemma3:27b 3짝 = 278짝 |
| 분할(문서 단위, `sha1(doc_id) % 10`: 0=test, 1=valid, 나머지 train) | train 245 / valid 17 / test 16 (`data/v0-dryrun/`) |
| 학습 | `gogamza/kobart-base-v2`(124M) 전체 파인튜닝, MPS, seed 0, lr 3e-5, batch 8, 2 epoch, **20.6초** |
| valid loss | 3.07 → 2.72 |
| ONNX 변환 | encoder / decoder(KV 캐시 없음) 두 그래프, opset 17 |
| INT8 동적 양자화 | onnxruntime `quantize_dynamic`(QInt8) |
| 모델 폴더 크기 | **164.6 MB** (encoder 66.7MB + decoder 104.3MB + tokenizer 1.5MB + metadata·parity). 기준 300MB 이하 ✅ (KV 캐시 적용 후 164.4MB) |
| metadata.json | `version, created_at, data_snapshot, base_model, metrics`(학습 설정·이력·폴더 크기) |
| parity.jsonl | 고정 입력 20문장(`training/export.py` `PARITY_INPUTS`)과 학습 환경 출력. 다시 불러 돌린 결과 **20/20 일치** |

## CPU 추론 시간 (이 Mac, M5 Ultra, onnxruntime CPU, 스레드 1개)

| 입력 | 문장당 |
|---|---|
| parity 20문장(평균 45자) | 평균 0.145s, p50 0.116s, p95 0.353s, 최대 0.52s |
| 78자(수집 문장 중앙값) | 0.19s |
| 160자(95분위) | 0.82s |
| 198자(최장) | **1.54s** ❌ (기준 1초 초과) |

- 불러오기 0.32s, 프로세스 최대 RSS 330MB.
- Lightsail(2 vCPU)에서는 재지 않았다 [미확인]. 이 Mac보다 느릴 것이므로 긴 문장은 확실히 1초를 넘는다.
- 원인: KV 캐시 없이 매 토큰마다 디코더를 전체 길이로 다시 돈다(O(n²)). → 아래 "KV 캐시 적용(이슈 #2)"에서 해결.

## KV 캐시 적용 (이슈 #2)

- `encoder.onnx`: 원문 → 디코더 6개 층의 cross-attention K/V(한 번만 계산).
- `decoder.onnx`: 토큰 1개 + `position_ids` + 층별 self-attention 과거 K/V(첫 단계는 길이 0) + cross K/V → logits, 새 self K/V. HF BART 디코더 층(post-LN)을 `training/export.py`에서 그대로 따라 짰다.
- `simple_word.model.Simplifier`는 한 토큰씩 넣고 K/V를 이어 붙인다. 인터페이스(약속 1)는 그대로다.

### 정확성

| 확인 | 결과 |
|---|---|
| `tests/test_simplifier.py` 작은 랜덤 BART: ONNX(fp32) 탐욕 = torch `generate` 탐욕 | 통과 |
| 실제 v0-dryrun 모델 fp32 ONNX(KV 캐시) vs torch `generate` 탐욕, parity 20문장 | **20/20 일치** |
| INT8 모델 parity 다시 불러 실행(학습 환경 = 서빙 경로) | **20/20 일치** |
| 새 INT8(KV 캐시) vs 옛 INT8(캐시 없음) 출력 | 11/20 같음 |
| fp32 기준과 같은 INT8 출력 | 옛 2/20, 새 4/20 |

- INT8 출력이 바뀐 이유는 그래프가 아니라 **동적 양자화** 때문이다. 활성값 스케일을 입력 텐서 전체에서 계산하는데, 캐시가 없을 때는 지금까지의 모든 토큰을, 캐시가 있을 때는 새 토큰 1개만 보고 계산한다. fp32에서는 두 방식이 torch와 20/20 같으므로 디코딩 로직은 맞다.
- 2 epoch만 돌린 모델이라 1·2위 토큰 차이가 작아 INT8 오차에 쉽게 뒤집힌다. 실제 학습 후 INT8 vs fp32 일치율이 낮으면 정적 양자화(보정 데이터)나 decoder의 `lm_head`만 fp32로 두는 방안을 본다 [미실험].
- parity 게이트(학습 환경 출력 = 서빙 컨테이너 출력)는 같은 INT8 파일과 같은 코드를 쓰므로 영향 없다. 모델을 바꾸면 parity.jsonl도 새로 만든다.

### 전후 비교 (INT8, 이 Mac M5 Ultra, onnxruntime CPU 스레드 1, 긴 문장은 3번 중 최소)

| 입력 | 캐시 없음 | KV 캐시 |
|---|---|---|
| 45자(parity 20문장 평균) | 평균 0.145s, p95 0.353s, 최대 0.52s | 평균 **0.038s**, p95 **0.069s**, 최대 0.095s |
| 78자 | 0.19s (출력 77자) | **0.047s** (출력 80자) |
| 160자 | 0.82s (출력 163자) | **0.097s** (출력 158자) |
| 198자 | 1.54s ❌ (출력 222자) | **0.077s** ✅ (출력 111자) |
| 모델 폴더 | 164.6 MB (encoder 66.7 + decoder 104.3) | 164.4 MB (encoder 73.9 + decoder 97.0) |
| 불러오기 / 최대 RSS | 0.32s / 330MB | 0.27s / 321MB |

- 198자는 INT8 출력이 달라져 출력 길이가 222자→111자로 짧아졌으니 시간 비교에 감안할 것. 160자(출력 길이 비슷)에서 8.5배 빨라졌고, 이제 시간이 출력 토큰 수에 거의 비례한다(토큰당 약 1ms). 최대 생성 길이 256토큰이어도 약 0.3초다. **목표(198자 1초 이하) 달성.**
- Lightsail(2 vCPU)에서는 아직 재지 않았다 [미확인].
- 참고: fp32 ONNX 폴더는 648.6MB라서 서빙에는 INT8만 쓴다.

## 출력 예 (2 epoch·278짝이라 품질은 의미 없음)

- 입력: "과태료 부과 사전통지서를 송달받은 날부터 20일 이내에 … 100분의 20에 해당하는 금액을 감경합니다."
  출력: "과태료를 부과하겠다는 의견을 낸 날부터 20일 안에 의견제출하지 않은 날부터 20일 안에 내지 않은 날부터 …" (반복·뜻 변형)
- parity 입력 1~3번은 T2 실험 문장과 같아서 이번 학습 데이터에 들어 있었다. parity는 학습 환경=서빙 일치만 보는 용도라 상관없지만, 평가셋에는 넣지 말 것.

## 교사 작업과 병행 영향

- 교사(gemma3:27b) 생성 속도: 학습 전 90초당 43짝, 학습 중(26초) 환산 90초당 38짝 → 약 10% 감소, 짧아서 무시 가능. 실제 학습(수천 짝·여러 epoch)은 교사 생성이 끝난 뒤나 밤에 따로 돌린다.

## 구현 요약

| 파일 | 내용 |
|---|---|
| `training/train.py` | passed 짝만, 문서 단위 고정 분할 → `data/<version>/`, KoBART 전체 파인튜닝(MPS), 시드 고정·`use_deterministic_algorithms(warn_only)` → `models/<version>/hf/` |
| `training/export.py` | ONNX 변환, INT8 동적 양자화, tokenizer.json 복사, parity.jsonl·metadata.json, 폴더 크기 |
| `simple_word/model.py` | `Simplifier(artifact_dir).simplify(list[str]) -> list[str]`: onnxruntime CPU(스레드 1) 탐욕 디코딩(KV 캐시). `encoder.onnx`가 없을 때만 더미(입력 그대로) |
| `tests/test_train_split.py` | 같은 문서가 두 분할에 섞이지 않음, 결정적 |
| `tests/test_simplifier.py` | 더미 동작; 작은 랜덤 BART를 내보내 ONNX 탐욕 출력 = torch `generate` 탐욕 출력, 두 번 돌려도 같음 (torch 없으면 건너뜀) |

- 의존성: 서빙 `numpy, onnxruntime, tokenizers`(본 의존성), 학습 `pip install -e ".[train]"`(torch, transformers, onnx). 이 Mac은 python3.15용 torch가 없어 `uv venv -p 3.12`로 실행했다.
- 모델 파일은 `models/`(gitignore)에만 있고 커밋하지 않았다. `models/<version>/hf/`(474MB, fp32 체크포인트)는 서빙에 올리지 않는다.
