# GCP 기본 설정

프로젝트 `simple-word-515207`, 리전 `asia-northeast3`의 기본 자원을 `deploy/gcp/` 스크립트로 관리한다. 모든 gcloud 호출은 프로젝트를 명시하고, 기본 프로젝트 설정은 바꾸지 않는다.

## 실행

- `bash deploy/gcp/setup.sh`: API, 월 예산, Artifact Registry, 비공개 모델 버킷, 서비스 계정과 GitHub OIDC WIF를 멱등 생성한다.
- `IMAGE_TAG=커밋 bash deploy/gcp/publish.sh`: Cloud Run 호환 `linux/amd64` 이미지로 빌드해 `asia-northeast3-docker.pkg.dev/simple-word-515207/simple-word/api:<태그>`로 올린다.
- `IMAGE_TAG=커밋 bash deploy/gcp/deploy.sh`: 버킷의 registry가 `champion=v2`이고 canary/shadow가 없으며 `v2/{metadata.json,encoder.onnx,decoder.onnx}`가 모두 있을 때만 공개 Cloud Run 서비스를 배포한다. 설정은 최소 0, 최대 2 인스턴스, 1 GiB, 동시성 2다.

예산 계정 통화는 KRW다. 예산은 월 6,660원(설정 시 약 5 USD에 해당), 현재 지출의 50%·90%·100%에서 알림을 보낸다. 환율이 변해도 예산액은 고정이므로 `setup.sh`와 GCP 예산을 함께 조정한다. 알림 수신은 결제 계정의 기본 billing 관리자/사용자다.

## 생성한 리소스

- Artifact Registry: `asia-northeast3/simple-word`
- 비공개 Cloud Storage: `gs://simple-word-515207-models`, 균일 버킷 수준 접근, 공개 액세스 방지, `staging/` 객체 30일 후 삭제
- Cloud Run runtime 계정: `simple-word-runtime@simple-word-515207.iam.gserviceaccount.com` (버킷 객체 읽기)
- 배포 계정: `simple-word-deployer@simple-word-515207.iam.gserviceaccount.com` (Cloud Run developer, 저장소 writer, runtime 계정 사용)
- GitHub WIF: pool `simple-word-github`, provider `github-main`; 저장소 `deepbluemoon/simple-word`의 `main` ref만 허용
- Provider resource: `projects/610053006876/locations/global/workloadIdentityPools/simple-word-github/providers/github-main`
- 예산 ID: `1cdd521d-0564-4c7b-9591-589b5bc7fd77`
- 업로드 이미지: `api:latest`, digest `sha256:92dd0ea4f44d17448dfe398b2f0ab3a23c018b1b3d7957cc3bf26e7424cf49b9` (`linux/amd64`)

## 배포 대기 사유

이미지 `api:latest`는 Artifact Registry에 업로드했지만 모델 버킷은 비어 있다. 현재 작업 사본에도 v2 ONNX 파일이 없다. 앱은 registry가 없으면 dummy로 기동할 수 있으므로, v2만 배포한다는 조건을 지키기 위해 Cloud Run 서비스는 만들지 않았다. Max Mac에서 v2의 `models/registry.json` 및 `models/v2/{metadata.json,encoder.onnx,decoder.onnx}`를 버킷 루트에 올린 후 `deploy.sh`를 실행한다.
