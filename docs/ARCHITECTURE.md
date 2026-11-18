# 아키텍처 (초안, T1)

모델 종류와 학습 데이터는 T2 조사 결과에 따라 정한다. 이 문서는 모듈 경계와 약속(인터페이스)을 먼저 고정해서 각 에이전트가 병렬로 작업하게 하는 것이 목적이다.

## 흐름

```
[사용자] 파일 업로드 (txt, pdf, docx, hwpx)
   ↓
[api] POST /simplify ─ 파일→텍스트 → 문장 분할 → 라우터 ─┬─ champion 모델 → 응답
                                                         ├─ canary 모델 (트래픽 일부) → 응답
                                                         └─ shadow 모델 (기록만, 응답 안 함)
   ↓ 요청·응답·모델 버전 로그
[monitor] 카나리·섀도 지표 비교 → 나쁘면 롤백

[공급원] 보도자료·공고문 등 새 공문서 → [teacher] Ollama가 쉬운 말 짝 생성
   ↓
[training] 데이터 스냅샷 → 학습 → 평가 → 모델 아티팩트
   ↓
[gate] champion 대비 성능 + parity 검증 → 통과 시 registry에 등록 → canary로 시작
```

## 디렉토리와 담당

| 경로 | 내용 | 담당 |
|---|---|---|
| `simple_word/model.py` | 추론 인터페이스 (아래 약속 1) | Claude Max |
| `training/` | 데이터 수집·전처리, 교사 모델 짝 생성, 학습, 평가 | Claude Max |
| `api/` | FastAPI, 파일→텍스트, 라우터 | Codex |
| `web/` | 업로드 화면 (정적 HTML/JS, api가 서빙) | Claude Max |
| `gate/` | 게이트·parity 검증 스크립트 | Codex |
| `.github/workflows/` | CI/CD | Codex |
| `deploy/` | Dockerfile, 배포·롤백 스크립트 | Codex |
| `tests/` | 각 모듈 테스트 | 각 담당 + Codex 리뷰 |

## 약속

### 1. 추론 인터페이스
```python
class Simplifier:
    def __init__(self, artifact_dir: str): ...
    def simplify(self, sentences: list[str]) -> list[str]: ...
```
- 입력과 출력의 길이와 순서가 같다.
- 같은 입력에는 같은 출력이 나온다(결정적 디코딩). parity 검증의 전제다.

### 2. 모델 아티팩트
`models/<version>/` 디렉토리 하나가 모델 하나다.
- 모델 파일들
- `metadata.json`: `version`, `created_at`, `data_snapshot`, `base_model`, `metrics`
- `parity.jsonl`: 고정 입력 문장과 학습 환경에서 나온 출력. 서빙 환경이 같은 출력을 내는지 확인하는 데 쓴다.

### 3. 레지스트리 (Lightsail 버킷)
`registry.json` 하나로 지금 어떤 모델이 무슨 역할인지 정한다.
```json
{"champion": "v3", "canary": "v4", "canary_weight": 0.1, "shadow": null}
```
- 배포 = 이 파일을 바꾸는 것. 롤백 = 이전 버전으로 되돌리는 것.
- api는 이 파일을 주기적으로 다시 읽는다.

### 4. API
- `POST /simplify` (multipart 파일) → `{"model_version": "...", "sentences": [{"original": "...", "simple": "..."}]}`
- `POST /feedback` → 사용자 평가(좋아요/싫어요)를 기록. 카나리 판정에 보조 지표로 쓴다.
- `GET /health` → 로드된 모델 버전들

## 미정 (T2 이후)
- 모델: 문장 생성 모델(KoBART·KoT5 계열 소형)을 증류할지, 다른 방식인지.
- 평가 지표: 쉬운 말 변환은 정답이 하나가 아니다. 후보는 원문 대비 의미 보존 점수, 읽기 쉬움 점수, Ollama 교사 모델의 채점.
- 서빙 메모리: Lightsail은 메모리가 1.9GB다. champion·canary·shadow 세 모델을 동시에 올리려면 모델이 작아야 한다(INT8 양자화 등).
