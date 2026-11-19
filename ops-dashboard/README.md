# Simple Word 운영 대시보드

로컬 Docker Compose의 `simpleword-*` 컨테이너와 선택한 AWS Lightsail Docker Engine을 관측하고 AWS·GCP 상태와 월 비용을 함께 보여준다. 원본 운영 화면의 디자인과 기능을 유지하며 서버와 대시보드는 `127.0.0.1`에만 바인딩한다.

## 기능

- 실행·중지 컨테이너, 5초 간격 CPU·메모리 사용량, 최근 5분 그래프와 80% 경고를 제공한다. 경고 시작·해제에는 지속시간 히스테리시스를 적용한다.
- 선택한 컨테이너의 타임스탬프 로그를 실시간 스트리밍하고 INFO·WARN·ERROR를 구분한다. HTTP 상태코드 집계와 태그·경고를 제공한다.
- 오류코드에 연결된 진단 스크립트는 비활성 상태로 시작한다. 실행 전 대상을 확인하고 실행 이력 JSONL, 보고서 다운로드, 30일 정리를 지원한다.
- 패키지 화면은 프로젝트 `pyproject.toml`과 `ops-dashboard/package.json`을 기준으로 설치된 버전, OSV 권고, PyPI·npm 릴리즈와 GitHub Release 정보를 확인한다. 업데이트는 수동으로 적용한다.
- 클라우드 화면에서 Lightsail 컨테이너, GCP Cloud Run 상태·메트릭·로그, 실제 비용(설정된 경우), 공시 단가 기반 월 비용 예측을 확인한다.

## 실행

프로젝트 루트에서 `ops-dashboard/.env.example`을 참고해 `.env`를 만들고 필요한 자격 정보만 설정한다. `.env`는 Git에서 제외된다.

```bash
npm run check --prefix ops-dashboard
npm test --prefix ops-dashboard
npm run test:coverage --prefix ops-dashboard
npm start --prefix ops-dashboard
```

대시보드는 `http://127.0.0.1:9760`에서 열린다. 실행 이력, 보고서, 로그 보관 파일은 프로젝트 루트의 `.ops-data/`에 생성되며 Git에서 제외된다.

## Docker 대상

기본 감시 범위는 컨테이너 이름이 `simpleword-`로 시작하는 로컬 Compose 컨테이너다. Lightsail도 함께 조회하려면 `.env`에 SSH 호스트를 지정한다. 같은 Docker CLI 모듈이 원격 호출마다 `DOCKER_HOST=ssh://<AWS_SSH_HOST>`를 사용한다.

```dotenv
AWS_SSH_HOST=ubuntu@lightsail.example.com
```

SSH 키와 Docker Engine 접근이 준비되어 있어야 한다. Lightsail에는 자동 확장이 없고, 로컬 서비스 확장도 기본 허용 목록이 비어 있어 비활성이다. 실제 서비스가 검토된 뒤에만 `OPS_SCALE_SERVICE`와 `OPS_SCALE_ALLOWED_SERVICES`를 명시한다.

## 패키지 상태와 커버리지

파이썬 버전은 프로젝트 `.venv`에서 가져오며 `OPS_PYTHON`으로 인터프리터를 지정할 수 있다. npm 패키지는 `package.json`과 설치된 `node_modules/.package-lock.json`을 사용한다. 설치 버전을 확인할 수 없는 의존성은 취약점 검사 대상에 포함하지 않는다.

`npm run test:coverage --prefix ops-dashboard`는 Node 내장 coverage로 Docker·모니터링·HTTP 상태 집계·오류 및 실행 이력 모듈의 line·branch·function 각각 80%를 요구한다. 제공자·외부 API와 HTTP 서버 조정 코드는 통합 테스트로 확인한다. 테스트 임시 파일은 저장소 안 `.tmp/`에 둔다.
