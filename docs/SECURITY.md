# 보안 경계와 남은 위험

외부 입력은 인터넷 사용자의 파일·피드백과, 교사가 변환할 정부 문서다. 서비스는 5 MiB 업로드 상한과 문장·압축 해제 크기 상한을 유지하고, nginx에서도 느린 전송과 과도한 요청을 제한한다.

| 위협 | 대응 | 남은 위험 |
|---|---|---|
| DoS·자원 고갈 | nginx가 기본값으로 IP별 `/simplify` 10회/분(버스트 5), `/feedback` 30회/분(버스트 10), 동시 연결 20개로 제한하고 초과 시 `Retry-After`와 JSON 본문을 담은 429를 반환한다. 값은 `NGINX_*` 환경변수로 조정한다. 요청당 5 MiB API 상한, nginx 6 MiB body 상한, 2개 추론 슬롯, 읽기·전송 타임아웃을 둔다. 롤링 배포 때 임시 컨테이너에서 새 프록시 설정을 렌더링하고 기존 nginx에서 `nginx -t` 후 reload한다. | IP 기반 제한은 NAT·공유망 사용자를 함께 제한하며, 분산된 여러 IP의 공격은 막지 못한다. Route 53·클라우드 방화벽 수준 방어는 별도다. |
| 업로드 폭탄·파서 DoS | PDF는 `.pdf` 확장자나 `application/pdf` MIME 유형이면 API에서 파일 내용을 읽거나 PDF 파서를 호출하기 전에 415로 거절한다. DOCX/HWPX는 ZIP 해제 크기 20 MiB, 변환 입력은 최대 100문장으로 제한한다. | Starlette는 경로 함수 전에 multipart를 파싱하고 업로드를 임시 저장할 수 있다. API 컨테이너를 직접 외부에 공개하지 말고 nginx의 6 MiB 요청 상한을 유지해야 한다. DOCX/HWPX의 압축 해제와 XML 파싱에도 계속 자원 상한이 필요하다. |
| XML entity 폭탄·XXE | `defusedxml`로 DOCX/HWPX XML을 읽고 DTD/entity 선언을 거부한다. 잘못된 문서는 400이다. | 라이브러리 취약점은 업데이트와 함께 재검토해야 한다. |
| XSS·클릭재킹 | CSP(`default-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, Referrer-Policy를 응답에 붙인다. Pretendard 글꼴 CDN을 style/font/connect 출처에 허용한다. Vue의 진행 막대가 동적 인라인 스타일을 쓰므로 `style-src 'unsafe-inline'`도 허용하고 스크립트는 same-origin 정책을 유지한다. Vue 텍스트 보간을 사용하고, 예외적인 `v-html`은 HTML 이스케이프 뒤 고정 `<b>` 서식만 만든다. | 스타일 인라인은 허용하지만 인라인 스크립트는 허용하지 않는다. CSP는 같은 출처에 배포된 악성 스크립트나 브라우저 취약점을 막지 못한다. |
| 교사 프롬프트 인젝션 | 프롬프트 판 `v3-injection-guard`는 원문을 `<원문>` 경계로 감싸고 그 안의 지시는 따르지 말라고 명시한다. 교사 짝 검사는 숫자·보존 용어·조건·영어·길이·줄 수를 확인한다. | 프롬프트 지시만으로 인젝션을 완전히 막을 수 없다. 사람 검토와 고정 평가셋, BERTScore·게이트가 의미 훼손을 추가로 살펴야 한다. |
| 피드백 데이터 오염 | `feedback.jsonl`은 기본 자동 학습 입력이 아니다. 각 항목은 `request_id`, `result_id`, `sentence_index` 키를 가지며, 같은 키의 마지막 기록만 유효하다. `python scripts/review_feedback.py logs/feedback.jsonl`로 최신 투표를 확인한다. 자동 파이프라인은 피드백 파일을 읽지 않는다. 승인 항목은 사람과 총괄이 수동 선별해 별도 학습 입력으로 옮긴다. | 수동 선별에서 검토를 누락하거나 잘못 승인할 수 있다. |
| 로그 디스크 고갈·민감정보 | 요청·피드백 로그 각각 현재 파일 10 MiB와 최대 3개 회전본으로 제한한다. 여유 공간이 50 MiB 미만이거나 기록이 실패하면 경고 후 기록을 멈추며, 피드백 요청에는 503을 반환한다. 알려진 이메일·전화번호·주민번호 형식은 저장 전에 가린다. | 로그는 회전 시 오래된 기록이 삭제된다. 패턴에 잡히지 않는 개인정보·문서 내용은 남을 수 있으므로 로그 볼륨 접근을 제한하고 보존 기간을 정해야 한다. |
| 데이터베이스 질의 조작(SQL injection) | 현재 DB와 SQL 질의가 없다. 파일은 JSONL로 추가 기록한다. | 향후 DB를 추가하면 파라미터화 질의와 권한 분리를 적용해야 한다. |

피드백 API는 사용자의 의견을 수집할 뿐 학습을 직접 시작하지 않는다. 평가셋은 학습 데이터와 분리해 유지한다. CSP 브라우저 검사는 개발 서버나 테스트가 주입한 헤더가 아니라 Compose nginx가 제공한 빌드 앱과 실제 응답 헤더를 사용한다. 보안 변경 검증은 `simple-word:qa-sec`와 전용 Compose 프로젝트로 수행하며, `simple-word:local`과 nightly의 18016 포트는 사용하지 않는다.

`PROMPT_VERSION`은 생성된 학습 짝의 프롬프트 변경 이력을 표시하며 모델 버전은 뜻하지 않는다.
