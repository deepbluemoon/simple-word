# 운영 대응 스크립트

## 실행 원칙

- 경고는 대응 옵션을 활성화할 뿐 스크립트를 자동 실행하지 않는다. 실행 전 대화상자에서 대상과 영향을 확인한다.
- 로그 수집은 선택 사항이다. 알려진 패턴을 마스킹해도 비밀정보 제거를 보장하지 않으므로 공유 전 결과를 확인한다.
- 실행 이력, 보고서, 로컬 컨테이너 로그는 프로젝트 루트 `.ops-data/`에만 저장한다. 디렉터리는 Git에서 제외된다.

## 제공 스크립트

### 컨테이너 장애 정보 수집

- 파일: `scripts/collect-container-incident.sh`
- 활성 코드: `OPS-CPU-80-001`, `OPS-MEM-80-001`, `HTTP-5XX-RATE-001`
- 선택한 컨테이너의 이미지, 상태, 종료 코드, 종료 시각, 재시작 횟수, health 상태를 기록한다. 선택하면 최근 100줄의 로그(최대 256 KiB)도 포함한다.
- 보고서는 `.ops-data/reports/incident.*/incident.txt`에 저장한다. 컨테이너·서비스는 변경하지 않는다.

### Docker 연결 점검

- 파일: `scripts/check-docker-access.sh`
- 활성 코드: `OPS-DOCKER-001`
- Docker CLI·context·Engine 연결 결과를 보여준다. 읽기 전용이다.

### Compose 서비스 확장

- 파일: `scripts/scale-service.sh`
- 활성 코드: `OPS-CPU-80-001`, `OPS-MEM-80-001`
- 기본 허용 목록과 대상 서비스가 비어 있어 비활성 상태다. Lightsail은 자동 확장을 지원하지 않아 원격 컨테이너의 확장 요청은 거부한다.
- 검토된 로컬 무상태 서비스만 `OPS_SCALE_SERVICE`와 `OPS_SCALE_ALLOWED_SERVICES`에 명시해 활성화할 수 있다. 사전 점검은 Docker Engine, Compose 서비스, 허용 목록, replica 상한을 확인하며 축소와 데이터베이스 확장을 막는다.
- 실행 전 확인 후에도 사후 health 확인 실패 시 자동 롤백하지 않는다. 현재 replica와 서비스 상태를 확인해 사람이 복구를 결정한다.

## 이력과 보관

- 감사 이력은 `.ops-data/action-audit.jsonl`, 진단 보고서는 `.ops-data/reports/`, 컨테이너 로그는 `.ops-data/logs/`에 둔다.
- 보고서는 대시보드에서 다운로드·개별 삭제할 수 있고 30일 지난 보고서를 확인 후 정리한다.
- 로그 파일은 컨테이너 ID별로 분리하며 10 MiB씩 최대 5개, 기본 30일 보관한다. `OPS_LOG_ARCHIVE_DIR`, `OPS_LOG_ARCHIVE_MAX_FILE_BYTES`, `OPS_LOG_ARCHIVE_MAX_FILES`, `OPS_LOG_ARCHIVE_RETENTION_DAYS`로 조정할 수 있다.
