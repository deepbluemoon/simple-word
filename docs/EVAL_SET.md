# 사람 검수 평가셋 200건 (이슈 #7, T11)

작성: Claude Max, 2026-11-19. 스크립트는 `training/eval_set.py`이다. 후보·CSV·평가셋 파일은 `data/eval/`(gitignore)에만 둔다.

## 검수하는 사람이 할 일

1. `data/eval/review.csv`를 엑셀이나 Numbers로 연다(UTF-8 BOM이라 한글이 깨지지 않는다).
2. 각 행의 **제안 쉬운 말**을 읽는다.
   - 맞으면 **고친 쉬운 말**을 비워 둔다. 그러면 제안이 그대로 정답이 된다.
   - 틀리거나 어색하면 **고친 쉬운 말**에 바른 문장을 쓴다. 숫자·날짜·금액·법령·기관명은 원문 그대로 둔다.
   - 평가에 쓰기 어려운 문장(원문이 잘렸거나, 표 조각이거나, 뜻을 알 수 없음)은 **메모**를 `제외`로 시작하게 쓴다. 예: `제외: 표 조각`.
3. **id**와 **원문** 열은 고치지 않는다. 원문이 후보와 다르면 읽어 들일 때 멈춘다.
4. **메모**에는 `[제안=v2 출력]`이나 `[제안=교사 출력 …]`이 미리 들어 있다. 제안이 어디서 왔는지 알려 주는 표시이며 지우거나 덮어써도 된다.
5. CSV로 저장한다(형식: CSV UTF-8).

행 하나에 1분이면 200건을 3~4시간에 끝낼 수 있다 [추정].

## 명령

```
# 1. 후보 200건 (원문·교사 출력·v2 출력·fallback 여부)
python -m training.eval_set candidates --pairs data/pairs.jsonl --splits data/v2 --model models/v2   # → data/eval/candidates.jsonl
# 2. 검수 CSV
python -m training.eval_set export-csv                                    # → data/eval/review.csv
# 3. 검수 끝난 CSV → 평가셋 (src, ref, edited, stratum, doc_id, memo)
python -m training.eval_set import-csv                                    # → data/eval/eval_set.jsonl
# 4. 누수 검사: eval_set_overlap 이 0이어야 한다
python -m training.train --version v2 --pairs data/pairs.jsonl --split time --docs data/docs.jsonl \
  --eval-set data/eval/eval_set.jsonl --check-leakage
```

- 정답(`ref`)은 **고친 쉬운 말**이 있으면 그것이고, 비어 있으면 **제안 쉬운 말**이다. `edited`가 사람이 고쳤는지 표시한다.
- 앞으로 학습할 때는 항상 `--eval-set data/eval/eval_set.jsonl`을 넘긴다. 그러면 `train()`이 평가셋 문장이 train에 들어간 것을 보고 학습을 거부한다(`training/train.py` `leakage`). 지금 후보는 모두 교사 검사에서 탈락한 짝이다. 나중에 교사를 다시 돌리거나 검사 규칙을 바꾸면 이 문장들이 train에 들어올 수 있다.

## 어디서 뽑았나

- 모은 짝: `data/pairs.jsonl`의 3,348개.
- 뺀 것: v2 학습에 쓴 `data/v2/{train,valid,test}.jsonl` 2,053문장과 고정 parity 입력 20문장. 같은 문장과 유사 중복(한글만 남겨 같음, `training.train._near`)을 모두 뺐다. 후보끼리의 유사 중복도 뺐다.
- 남은 것(풀): **1,295문장**. v2 분할은 교사 검사를 통과한 짝만 쓰므로, 풀은 모두 **교사 검사에서 탈락한 짝**의 원문이다.
- 뽑기: 층별로 seed 0으로 섞어 정해진 수만큼 뽑는다. 결정적이라 다시 돌려도 같은 200건이 나온다.

### 층(stratum)

한 문장이 여러 층에 해당하면 표에서 위에 있는 층에 넣는다. 드문 층부터 채우려는 순서다.

| 층 | 판정 | 목표 | 풀 | 뽑음 | v2 fallback | 원문 길이 중앙값 |
|---|---|---|---|---|---|---|
| `preserve` 보존 용어 | `simple_word/preserve_terms.txt`의 용어가 있음 | 30 | 184 | 30 | 14 | 89.5자 |
| `difficult` 국어원 어려운 용어 | `data/nikl_terms.csv`의 2글자 이상 용어가 있음 | 20 | 19 | **19** (풀 전부) | 4 | 79자 |
| `numbers` 숫자·날짜·금액 | `simple_word.numbers.numbers()`가 값을 찾음 | 60 | 467 | 60 | 20 | 56자 |
| `long` 긴 문장 | 100자 이상 (위 셋에 해당하지 않음) | 30 | 57 | 30 | 0 | 121자 |
| `general` 일반 | 위 넷에 해당하지 않음 | 60 | 568 | 61 (모자란 1건 채움) | 0 | 38자 |
| 합계 | | 200 | 1,295 | **200** | **38** | |

- 층은 우선순위대로 하나만 붙지만, 문장의 특징(`features`)은 모두 기록한다. 실제로 숫자가 든 문장은 92건이다(`numbers` 60 + `preserve` 24 + `difficult` 8). 100자 이상인 문장은 56건이다.
- 국어원 용어가 든 문장은 풀에 19개뿐이다(학습에 쓴 문장에도 test 186문장 중 2개였다). 모두 넣고 남은 1자리는 일반 문장으로 채웠다.

## 검수 파일(`data/eval/candidates.jsonl`) 항목

| 필드 | 뜻 |
|---|---|
| `id` | `e001`~`e200`. CSV와 평가셋에서 같은 값을 쓴다 |
| `doc_id`, `idx`, `doc_split` | 원문 위치. `doc_split`은 같은 문서의 다른 문장이 v2 어느 분할에 있는지다(없으면 null) |
| `stratum`, `features` | 층과 특징(숫자 값, 어려운 용어, 보존 용어, 긴 문장인지) |
| `src` | 원문 |
| `teacher`, `teacher_passed`, `teacher_reject` | 교사(gemma3:27b) 출력, 검사 통과 여부(모두 false), 탈락 사유 |
| `model`, `model_out`, `fallback` | v2 출력(숫자·보존 용어 안전장치 포함, INT8 ONNX)과 원문으로 대체됐는지 |

CSV의 **제안 쉬운 말**: v2가 원문 그대로 돌려줬으면(fallback 38건) 교사 출력을, 아니면 v2 출력을 넣었다. 교사 출력은 검사에서 탈락한 것이라 길거나, 줄이 여러 개이거나, 숫자가 틀릴 수 있다. 이 38건은 고칠 것이 많을 것이다.

## 한계

- **문서 단위로는 겹친다.** 200건 중 171건은 train에 쓴 문서에서 나왔다(valid 문서 13, test 문서 16). 문장은 다르지만 같은 보도자료의 다른 문장을 학습했으므로 성능이 실제보다 좋게 나올 수 있다. `--eval-set` 누수 검사도 문장 단위만 본다. 문서까지 떼려면 v2 이후(11-20 이후) 새로 모은 글에서 뽑아야 한다.
- **교사가 탈락시킨 문장만 있다.** 탈락 사유는 length 위주다(200건 중 length 포함 141). 원문이 어렵거나 길어 교사도 실패한 문장일 수 있어서, 평가가 쉬운 문장보다 어렵게 나올 수 있다 [미확인].
- 국어원 용어 층은 19건이라 이 층만의 비율은 오차가 크다.
