# 배포

## Lightsail

Lightsail은 현재 champion만 실행한다. nginx 뒤에 같은 이미지와 모델을 쓰는 `api-1`, `api-2`가 있고, nginx가 두 upstream에 부하를 나눈다. 연결·타임아웃·502·503·504 실패는 다른 upstream으로 재시도한다. Lightsail에는 카나리, 섀도, 오토스케일링이 없다.

초기 구성과 로컬 실행:

```sh
IMAGE=ghcr.io/OWNER/simple-word:VERSION docker compose -f deploy/compose.yaml up -d --build --wait api-1 api-2 proxy
```

새 GCP champion 검증은 GCP Cloud Run의 카나리 리비전 비율과 섀도 트래픽에서 끝낸 뒤 Lightsail에 롤링 반영한다. 현재 태그는 `deploy/common.sh`의 프로젝트·호스트별 상태 파일에 기록하고 이전 태그는 `.previous` 파일에 보관한다.

```sh
deploy/rolling.sh ghcr.io/OWNER/simple-word:VERSION
```

롤링 스크립트는 (설정된 경우) `WEIGHT_HOOK`을 `up` 인자로 실행하고 `WEIGHT_HOOK_WAIT`초(기본 30초) 기다린다. 이어 `api-1`, `api-2`를 차례로 교체하며 각각 컨테이너 health와 프록시 smoke를 확인한다. 성공하면 훅을 `restore` 인자로 실행해 가중치를 기본 90/10으로 돌린다. 실패하면 이미 교체한 컨테이너를 각자의 기존 이미지로 되돌리고 가중치도 복귀시킨다.

Route 53용 실행 파일은 아직 없다. 계정과 DNS 레코드에 맞춘 명령을 배포 호스트에서 `WEIGHT_HOOK`으로 지정한다. 예를 들면:

```sh
WEIGHT_HOOK='/usr/local/bin/set-route53-weight' WEIGHT_HOOK_WAIT=60 deploy/rolling.sh ghcr.io/OWNER/simple-word:VERSION
```

훅은 `up`이면 Lightsail/GCP 가중치를 임시 상향하고, `restore`이면 90/10으로 복구해야 한다. 훅 자체도 실패 코드를 반환해 배포를 중단시켜야 한다.

이전 champion으로 전환:

```sh
deploy/rollback.sh
```

`deploy.sh <image:tag>`도 `rolling.sh`를 호출한다. 모든 명령은 `DEPLOY_USER`/`DEPLOY_HOST` 또는 Docker context로 원격 배포를 지정할 수 있다. Route 53 헬스체크는 Lightsail 또는 GCP의 상태가 나쁘면 해당 위치를 라우팅에서 제외하며, 가중치 변경은 위 훅에 둔다.

## Cloud Run

GCP Cloud Run은 API, 웹, 모델/스토리지의 3티어다. 서비스는 1 GiB 메모리, 최소 인스턴스 1, 최대 3으로 운용한다. 새 모델은 Cloud Run 리비전 비율 카나리와 champion에 대한 섀도 평가를 거쳐 GCP champion이 된다. Lightsail 롤링 중에는 DNS 가중치를 일시 조정할 수 있고, 작업이 끝나면 기본 Lightsail 90 / GCP 10으로 복귀한다. 장애 조치에서는 Route 53 헬스체크가 살아 있는 쪽으로 트래픽을 보낸다.

## 로컬 검증

```sh
bash deploy/test-local.sh
```

이 테스트는 별도 Compose 프로젝트와 `simple-word:qa-codex` 이미지로 두 API를 띄운다. 롤링 도중 연속 health 요청에 5xx가 없는지, 잘못된 이미지 배포 뒤 교체한 컨테이너가 기존 태그로 복구되는지 확인한다. 18016 nightly 서비스, `simple-word:local` 이미지는 사용하지 않는다.
