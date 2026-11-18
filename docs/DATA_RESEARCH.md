# T2 데이터 조사 (DATA_RESEARCH)

작성: Claude Max (브랜치 `max/t2-data-research`), 2026-11-18
표기: [확인됨] = 이 세션에서 직접 열어/호출해 확인(근거 첨부), [미확인] = 직접 확인 못 함.

## 1. 이 머신 환경 [확인됨: 로컬 명령 출력]

| 항목 | 값 |
|---|---|
| hostname | Studio-C |
| CPU | Apple M5 Ultra, 30 코어 (`hw.ncpu`) |
| 메모리 | 96 GiB (통합 메모리, `hw.memsize`=103079215104) |
| GPU | Apple M5 Ultra 내장 GPU 64코어, Metal 4 (CUDA 없음) |
| 디스크 | / 926Gi 중 748Gi 여유 |
| OS | macOS 27.0.1 |
| Ollama | 0.40.10 |

`ollama list`:

| 모델 | 크기 | 용도 메모 |
|---|---|---|
| qwen3-4b-64k:latest | 2.5 GB | qwen3 4B 컨텍스트 64k 변형 |
| gemma3:4b | 3.4 GB | 다국어 4B |
| bge-m3:latest | 1.2 GB | 임베딩(생성 불가) |
| qwen3:4b-instruct-2507-q4_K_M | 2.5 GB | qwen3 4B instruct Q4 |

시사점: 96GB 통합 메모리면 교사 모델로 27B~70B급(Q4)도 로컬 구동 가능. 현재 설치 모델은 모두 4B급이라 교사로는 약함 → 4절 참조.
배포 대상 Lightsail(2 vCPU, 1.9GB RAM, GPU 없음)은 학생 모델이 매우 작아야 함(≤1B, 양자화 또는 seq2seq 소형).
