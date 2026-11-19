# Ops Dashboard

로컬 Mac에서 AWS와 GCP 상태 및 월 비용을 확인하는 대시보드입니다. HTTP 서버는 항상 `127.0.0.1`에만 바인딩합니다.

```sh
cp ops-dashboard/.env.example ops-dashboard/.env
# .env에 AWS_SSH_HOST, GCP_PROJECT 등 필요한 값 입력
npm run dev --prefix ops-dashboard
open http://127.0.0.1:9760
node --test ops-dashboard
```

환경 변수는 선택 사항이며 비어 있으면 해당 클라우드를 `미연결`로 표시합니다.

| 변수 | 기본값 | 용도 |
|---|---|---|
| `OPS_DASHBOARD_PORT` | `9760` | 로컬 포트 |
| `OPS_DASHBOARD_POLL_MS` | `30000` | 상태 갱신 주기(ms) |
| `AWS_SSH_HOST` | 없음 | SSH config에 등록한 AWS Docker 호스트 |
| `GCP_PROJECT` | 없음 | Cloud Run 프로젝트 ID |
| `GCP_REGION` | `asia-northeast3` | Cloud Run 리전 |
| `GCP_BILLING_TABLE` | 없음 | 실제 비용 조회용 BigQuery Billing Export `project.dataset.table` |
| `USD_KRW` | `1350` | USD→KRW 표시 환율 |

AWS 조회는 SSH로 Docker의 `ps`, `stats`만 실행합니다. GCP 조회는 gcloud CLI의 Cloud Run, Cloud Monitoring, Cloud Logging 읽기 명령만 사용합니다. 실제 비용은 AWS Cost Explorer와 BigQuery Billing Export 접근이 각각 가능할 때만 표시하며, 그 외에는 `src/prices.json`의 예상 가격을 표시합니다. 예상치의 가격 출처·확인일과 사용량 가정은 같은 파일에 기록했습니다.

GCP 계정은 Cloud Run Viewer, Monitoring Viewer, Logs Viewer와 Billing Export 테이블 읽기 권한만 부여하세요. AWS 실제 비용 조회에는 로컬 AWS CLI 프로필에 Cost Explorer 읽기 권한이 필요합니다. `.env`와 자격 증명은 저장소에 커밋하지 마세요.
