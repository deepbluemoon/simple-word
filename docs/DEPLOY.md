# 배포 사용법

`deploy/compose.yaml`은 API 두 개(`api`, `canary`)와 트래픽 분배 프록시를 실행합니다. Docker Engine과 Compose v2가 필요합니다. 릴리스 이미지는 먼저 GHCR 같은 레지스트리에 올려야 합니다.

## Lightsail 대상 설정

배포를 실행하는 사용자 계정에 Lightsail 호스트의 SSH 공개키 로그인이 설정되어 있어야 합니다. 원격 호스트에는 Docker Engine/Compose 플러그인과 이미지 레지스트리 pull 권한을 준비합니다. 레지스트리 토큰은 원격 호스트의 Docker credential store 또는 비밀 관리 기능에 등록하고 저장소에 넣지 마세요.

```sh
export DEPLOY_HOST=lightsail.example.com
export DEPLOY_USER=ubuntu
export HOST_PORT=8000
export MODEL_DIR=/srv/simple-word/models
export COMPOSE_PROJECT_NAME=simple-word
deploy/deploy.sh ghcr.io/OWNER/simple-word:VERSION
```

`DEPLOY_HOST`와 `DEPLOY_USER`는 SSH Docker endpoint(`ssh://user@host`)로 사용됩니다. `MODEL_DIR`은 Docker 호스트에 존재하는 모델 폴더이며 읽기 전용으로 마운트됩니다. 배포 상태 파일은 기본적으로 실행 사용자 홈의 `~/.simple-word/` 아래에 기록합니다. CI에서 실행한다면 `DEPLOY_STATE_FILE`을 지속 가능한 경로로 지정하세요.

`deploy.sh <image:tag>`는 지정한 태그로 `api`를 교체하고 컨테이너 및 프록시 healthcheck를 기다립니다. 실패하면 배포 직전 실행 중이던 태그를 다시 올립니다. 성공하면 직전 태그를 상태 파일에 저장합니다.

```sh
deploy/rollback.sh
```

`rollback.sh`는 상태 파일의 직전 태그를 배포합니다. 되돌린 뒤 현재 태그를 상태 파일에 저장하므로 다시 실행하면 두 버전 사이를 전환할 수 있습니다.

## Canary 배포

```sh
CANARY_PERCENT=10 \
CANARY_SAMPLE_SIZE=100 \
CANARY_SAMPLE_PATH=/ \
MAX_ERROR_RATE=0.01 \
deploy/canary.sh ghcr.io/OWNER/simple-word:VERSION
```

스크립트는 두 번째 `canary` 서비스를 띄워 healthcheck를 확인하고, 프록시의 요청 중 지정 비율을 canary로 보냅니다. `CANARY_SAMPLE_PATH`(기본 `/`)에 표본 요청을 보내 응답 헤더로 canary 요청 수와 오류율을 계산합니다. 최소 1개 canary 요청을 관측하고 canary 오류율이 `MAX_ERROR_RATE` 이하이면 새 태그를 `api`로 승격합니다. healthcheck, 표본 수, 오류율, 승격 healthcheck 중 하나라도 실패하면 트래픽을 안정 버전으로 돌리고 canary 서비스를 제거합니다.

## 로컬 검증

```sh
bash deploy/test-local.sh
```

검증 스크립트는 매번 고유한 Compose 프로젝트명을 사용하고, 사용 가능한 임의 포트를 골라 실행합니다. 성공 배포와 실패 배포의 자동 복구, 실패 canary 철회, 정상 승격, 실패한 명시적 롤백의 복구와 정상 롤백을 확인한 뒤 임시 프로젝트와 이미지, 볼륨을 정리합니다.

## 아직 클라우드가 필요한 작업

- GitHub Actions에서 이미지를 빌드해 GHCR 및 Artifact Registry에 올리고, Lightsail 배포와 GCP Cloud Run 배포에 Workload Identity를 연결하는 작업
- Route 53 헬스체크와 장애 조치 레코드 설정
- Lightsail 객체 스토리지, GCP 프로젝트 및 결제 계정, 도메인/호스팅 영역 준비
- 실제 장애 훈련을 수행하고 AWS↔GCP 전환 시간을 측정하는 작업
