# 배포

## Lightsail 호스트 준비와 HTTPS

호스트 초기화는 서비스 이미지를 올리지 않고 실행한다. 스크립트는 Docker Engine·Compose 플러그인, unattended-upgrades, fail2ban, UFW, 2 GiB 스왑, Sydney 시간·NTP, Docker 로그 제한과 `/srv/simple-word/{models,logs}`를 설정한다. SSH 비밀번호 인증을 끄기 전에 배포 사용자의 `authorized_keys`를 확인한다. `/etc/simple-word`는 root:docker 0750, `deploy.env`는 root:docker 0640이며 docker 그룹만 읽을 수 있다. docker 그룹은 root 권한과 동등하므로 신뢰할 전용 배포 계정만 추가한다.

```sh
ssh eta 'sudo env SIMPLE_WORD_DOMAIN=moon.eta.pyhub.kr bash -s' < deploy/bootstrap-lightsail.sh
```

Lightsail은 Caddy가 외부 80/443을 받고, 자동으로 HTTPS 인증서를 발급·갱신하며 HTTP를 HTTPS로 돌린다. Caddy는 내부 HTTP로 nginx에 전달한다. nginx와 API에는 호스트 포트를 게시하지 않는다. Caddy의 인증서와 ACME 계정은 프로젝트 이름이 유지되는 named volume `caddy_data`, `caddy_config`에 남아 컨테이너 교체 뒤에도 재사용된다. `/etc/letsencrypt`의 기존 파일과 설정은 bootstrap이 건드리지 않는다.

Caddy는 JSON 접속 로그를 `/data/access.json`에 기록한다. 로그에는 클라이언트 IP, 시간, 경로, 상태 코드와 지연이 남고 10 MiB 단위, 최근 5개 파일로 회전한다. 요청 헤더와 query string은 기록하지 않는다. 차단 IP/CIDR은 `deploy/blocklist.sh add 203.0.113.4` 또는 `remove 203.0.113.4`로 변경한다. 스크립트는 nginx 설정 검사에 성공한 뒤 reload하며 실패하면 파일을 원상 복구한다.

## Lightsail

Lightsail은 Caddy → nginx → `api-1`/`api-2` 구조다. Caddy만 80/443을 게시하고 nginx는 전용 edge/backend network, API는 내부 backend network에만 연결한다. Caddy는 edge network에서 `10.203.0.254`를 고정해 쓰고 nginx는 그 IP만 신뢰해 `X-Forwarded-For` 기준 사용자별 제한을 적용한다. Caddy는 기본 동작으로 외부에서 전달된 위조 `X-Forwarded-For` 값을 무시한다. Lightsail은 champion만 실행하며 카나리·섀도·오토스케일링은 없다.

초기 구성과 로컬 실행:

```sh
IMAGE=ghcr.io/OWNER/simple-word:VERSION docker compose -f deploy/compose.yaml up -d --build --wait api-1 api-2 proxy
```

새 이미지는 GCP 카나리와 섀도 트래픽으로 검증한 뒤 champion으로 승격하고 Lightsail에 롤링 반영한다. `Deploy verification` 재사용 워크플로는 같은 이미지·모델 버전으로 로컬 preflight를 실행하며, 향후 배포 워크플로가 GCP 카나리와 Lightsail 롤링 전에 이를 호출해야 한다. 현재 저장소에는 실제 클라우드 배포 호출자가 없다. 현재 태그는 `deploy/common.sh`의 프로젝트·호스트별 상태 파일에 기록하고 이전 태그는 `.previous` 파일에 보관한다.

```sh
deploy/rolling.sh ghcr.io/OWNER/simple-word:VERSION MODEL_VERSION
```

이미지 인자와 모델 인자를 주면 test-local은 해당 태그를 로컬에서 확인하거나 pull하고, 전달한 모델 디렉터리의 실제 `registry.json`을 사용한다. registry의 champion·canary·shadow 버전마다 artifact가 있는지 확인하고 smoke는 요청한 모델 버전이 로드되어 있는지 확인한다.

```sh
bash deploy/test-local.sh ghcr.io/OWNER/simple-word:VERSION /path/to/models MODEL_VERSION
```

롤링 스크립트는 모델 버전을 인자로 받는다. nginx 이미지를 갱신해 새 설정을 임시 컨테이너에서 렌더링하고, 기존 nginx 컨테이너에서 `nginx -t` 후 무중단 reload한다. 그 다음 (설정된 경우) `WEIGHT_HOOK`을 `up` 인자로 실행하고 `WEIGHT_HOOK_WAIT`초(기본 30초) 기다린다. 이어 `api-1`, `api-2`를 차례로 교체하며 컨테이너 health와 기대 모델이 로드된 smoke를 확인한다. Lightsail smoke는 API 컨테이너에서 내부 주소 `http://proxy:80`으로 직접 실행한다. 성공하면 훅을 `restore` 인자로 실행해 가중치를 기본 90/10으로 돌린다. 실패하면 이미 교체한 컨테이너를 각자의 기존 이미지로 되돌리고 가중치도 복귀시킨다.

Route 53용 실행 파일은 아직 없다. 계정과 DNS 레코드에 맞춘 명령을 배포 호스트에서 `WEIGHT_HOOK`으로 지정한다. 예를 들면:

```sh
WEIGHT_HOOK='/usr/local/bin/set-route53-weight' WEIGHT_HOOK_WAIT=60 deploy/rolling.sh ghcr.io/OWNER/simple-word:VERSION MODEL_VERSION
```

훅은 `up`이면 Lightsail/GCP 가중치를 임시 상향하고, `restore`이면 90/10으로 복구해야 한다. 훅 자체도 실패 코드를 반환해 배포를 중단시켜야 한다.

이전 champion으로 전환:

```sh
deploy/rollback.sh
```

롤백 smoke도 버전을 확인하므로 `EXPECTED_MODEL_VERSION=<이전 모델 버전> deploy/rollback.sh`로 실행한다.

`deploy.sh <image:tag> <model-version>`도 `rolling.sh`를 호출한다. 모든 명령은 `DEPLOY_USER`/`DEPLOY_HOST` 또는 Docker context로 원격 배포를 지정할 수 있다. Route 53 헬스체크는 Lightsail 또는 GCP의 상태가 나쁘면 해당 위치를 라우팅에서 제외하며, 가중치 변경은 위 훅에 둔다.

## Cloud Run

GCP Cloud Run은 API, 웹, 모델/스토리지의 3티어다. 서비스는 1 GiB 메모리, 최소 인스턴스 1, 최대 3으로 운용한다. 새 모델은 Cloud Run 리비전 비율 카나리와 champion에 대한 섀도 평가를 거쳐 GCP champion이 된다. Lightsail 롤링 중에는 DNS 가중치를 일시 조정할 수 있고, 작업이 끝나면 기본 Lightsail 90 / GCP 10으로 복귀한다. 장애 조치에서는 Route 53 헬스체크가 살아 있는 쪽으로 트래픽을 보낸다.

## 로컬 검증

```sh
bash deploy/test-local.sh
```

이 검증은 별도 Compose 프로젝트로 두 API와 Caddy를 띄운다. Caddy는 테스트용 내부 CA를 쓰며, 두 고정 IP 클라이언트로 사용자별 rate limit, 외부 XFF 위조 차단, blocklist의 403 응답과 JSON 로그를 확인한다. 이미지 인자를 주면 해당 이미지를 로컬에서 확인하고 없으면 pull하며, 그 이미지를 빌드하거나 삭제하지 않는다. 모델 인자를 주면 전달한 실제 registry와 champion·canary·shadow artifact를 검증해 그대로 사용한다. 롤링 도중 연속 health 요청에 5xx가 없는지, 잘못된 이미지 배포 뒤 교체한 컨테이너가 기존 태그로 복구되는지 확인한다. 인자 없이 PR에서 실행할 때는 `simple-word:qa-codex`와 더미 모델을 빌드한다. `Deploy verification`은 경로가 맞는 PR과 배포 파이프라인의 `workflow_call`로 실행하며, nightly·주간 예약은 두지 않는다. 18016 nightly 서비스, `simple-word:local` 이미지는 사용하지 않는다.
