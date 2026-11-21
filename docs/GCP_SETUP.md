# GCP 기본 설정

프로젝트 `simple-word-515207`, 리전 `asia-northeast3`의 기본 자원을 `deploy/gcp/` 스크립트로 관리한다. 모든 gcloud 호출은 프로젝트를 명시하고, 기본 프로젝트 설정은 바꾸지 않는다.

## 실행

- `bash deploy/gcp/setup.sh --project simple-word-515207`: API, 기존 월 예산, Artifact Registry, 비공개 모델 버킷, 서비스 계정과 GitHub OIDC WIF를 멱등 설정한다. 버킷 lifecycle은 `staging/` 정리 규칙만 교체하고 다른 규칙을 보존한다. 배포자는 `run.developer`와 `run.services.setIamPolicy` 단일 권한 커스텀 역할을 받는다. 예산만 안전하게 갱신하려면 `bash deploy/gcp/setup.sh --project simple-word-515207 --budget-only`를 쓴다.
- `IMAGE_TAG=커밋 bash deploy/gcp/publish.sh`: Cloud Run 호환 `linux/amd64` 이미지로 빌드해 `asia-northeast3-docker.pkg.dev/simple-word-515207/simple-word/api:<태그>`로 올린다.
- `IMAGE_TAG=커밋 bash deploy/gcp/deploy.sh`: 버킷의 registry가 `champion=v2`이고 canary/shadow가 없으며 `v2/{metadata.json,encoder.onnx,decoder.onnx}`가 모두 있을 때만 Cloud Run 서비스를 배포한다. 설정은 gen2, 최소 0, 최대 2 인스턴스, 1 GiB, 동시성 2다.

예산 계정 통화는 KRW다. 월 예산은 39,937원이다. 2026-11-20 USD/KRW 기준환율 1,331.24원을 적용해 30 USD를 원화로 환산하고 1원 단위로 반올림했다(30 × 1,331.24 = 39,937.2 KRW). 환율 출처: [WaveRate, 2026-11-20](https://waverate.app/rates/usd-to-krw). 알림 임계값은 현재 지출의 50%·90%·100%이며 수신자는 결제 계정의 기본 billing 관리자/사용자다. 예산 ID `1cdd521d-0564-4c7b-9591-589b5bc7fd77`를 수정하므로 재실행해도 중복 생성하지 않는다.

## 생성한 리소스

- Artifact Registry: `asia-northeast3/simple-word`
- 비공개 Cloud Storage: `gs://simple-word-515207-models`, 균일 버킷 수준 접근, 공개 액세스 방지, `staging/` 객체 30일 후 삭제
- Cloud Run runtime 계정: `simple-word-runtime@simple-word-515207.iam.gserviceaccount.com` (버킷 객체 읽기)
- 배포 계정: `simple-word-deployer@simple-word-515207.iam.gserviceaccount.com` (Cloud Run developer, 저장소 writer, 모델 버킷 객체 읽기, runtime 계정 사용)
- GitHub WIF: pool `simple-word-github`, provider `github-main`; 저장소 `deepbluemoon/simple-word`, owner ID `105283439`, `main` ref만 허용
- Provider resource: `projects/610053006876/locations/global/workloadIdentityPools/simple-word-github/providers/github-main`
- 예산 ID: `1cdd521d-0564-4c7b-9591-589b5bc7fd77`
- 업로드 이미지: `api:latest`, digest `sha256:92dd0ea4f44d17448dfe398b2f0ab3a23c018b1b3d7957cc3bf26e7424cf49b9` (`linux/amd64`)

## 현재 배포

Cloud Run `simple-word`는 v2 champion으로 배포되어 있다: https://simple-word-skjiwu6tcq-du.a.run.app . 서울 리전, gen2, 최소 0·최대 2 인스턴스, 1 GiB, 동시성 2이며 요청된 공개 서비스 설정을 사용한다. 재배포 스크립트는 registry에서 champion=v2, canary/shadow 비활성 상태와 필수 ONNX 파일을 확인한 뒤 실행한다. `--update-env-vars`로 기존 서비스 환경 변수는 보존한다. 공개 서비스 배포에는 `run.services.setIamPolicy`가 필요하며, 별도 CI 배포 경로에서 공개 접근이 승인되지 않았다면 `--allow-unauthenticated`를 제외한다.
