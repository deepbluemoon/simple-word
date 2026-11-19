# 모니터링 월

`/monitor.html`은 운영 대시보드의 별도 모니터링 화면이다. 짙은 바탕, 청록 강조, 큰 수치와 넓은 그래프 등 원본 디자인을 유지한다.

## 표시 항목

- 시스템 상태, 실행 컨테이너 수, CPU 합계, 메모리 실사용량
- 페이지를 연 뒤 수집한 최근 5분의 CPU·메모리 추이와 사용량 상위 5개
- 컨테이너 목록, HTTP 응답 구성, 활성 경고
- 전체 화면 전환과 운영 화면으로 돌아가는 링크

값은 실제 Docker 관측만 표시한다. 연결 실패, 오래된 관측, 빈 데이터는 정상 또는 0으로 표시하지 않는다. HTTP 분포는 컨테이너 로그에서 수집한 상태코드이며 요청량·지연시간을 의미하지 않는다.

## 확인 방법

프로젝트 루트의 `.env`에 다음처럼 범위를 설정하고 `npm start --prefix ops-dashboard`로 실행한다.

```dotenv
OPS_DASHBOARD_PORT=9760
OPS_DASHBOARD_HOST=127.0.0.1
OPS_CONTAINER_SCOPE=name
OPS_NAME_PREFIXES=simpleword-
```

운영 화면은 `http://127.0.0.1:9760/#overview`, 모니터링 화면은 `http://127.0.0.1:9760/monitor.html`이다. 주기 데이터는 5초마다 갱신된다.
