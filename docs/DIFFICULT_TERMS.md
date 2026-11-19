# 어려운 용어 사전 조사와 적용

## 조사한 출처

| 출처 | 형식·건수 | 라이선스와 활용 판단 | 받을 수 있는 곳 |
|---|---|---|---|
| 국립국어원 공공언어 쓰기 평가용 용어 목록 (15130006) | CSV, 1,331행 | 공공누리 제1유형: 출처 표시 후 상업적 이용·변경 가능. 기존 사전이며 계속 사용 | [공공데이터포털](https://www.data.go.kr/data/15130006/fileData.do), 실행 시 `data/nikl_terms.csv`로 내려받음 |
| 국립국어원 다듬은 말·우리말 다듬기 | HTML 목록 18,334건(기존 조사 기록); 2003년 합본 약 21,000개, 2004년 이후 자료 별도 누적 | 국립국어원 저작권 정책은 자료별 권리와 원 출처를 확인하도록 안내. 개별 항목의 상업적 이용·변경 허락이 확인되지 않아 제외 | [다듬은 말 검색](https://www.korean.go.kr/front/imprv/refineList.do?mn_id=158), [저작권 정책](https://www.korean.go.kr/front/page/pageView.do?page_id=P000508) |
| 법제처 법령정보지식베이스 법령용어-일상용어 연계 (15111331) 및 역방향 (15111333) | XML Open API, 실시간. 전체 건수 미공개; 활용 신청/인증키 필요 | 공공데이터포털에 “이용허락범위 제한 없음” 표시. 채택. API에서 받은 연계 XML은 `data/law_terms.xml`에 두며 사전은 `data/` 원본을 읽음 | [법령→일상용어](https://www.data.go.kr/data/15111331/openapi.do), [일상용어→법령](https://www.data.go.kr/data/15111333/openapi.do), [API 안내](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lstrmRltGuide) |
| 법제처 법령 정비용어 (15123435) | CSV, 21,735행 | 공공누리 제4유형: 상업적 이용·변경 금지. 제외 | [공공데이터포털](https://www.data.go.kr/data/15123435/fileData.do) |
| 법제처 일상용어 (15123793) | CSV, 81,970행 | 공공누리 제4유형: 상업적 이용·변경 금지. 제외 | [공공데이터포털](https://www.data.go.kr/data/15123793/fileData.do) |
| 공공용어 번역 정보 (15123639) | XLSX, 6,616행 | 공공누리 제1유형으로 이용 가능하지만 외국어 번역 대조표라 어려운 한국어-쉬운 한국어 짝이 아님. 목적에 맞지 않아 제외 | [공공데이터포털](https://www.data.go.kr/data/15123639/fileData.do) |
| 법제처 「알기 쉬운 법령 정비기준」 제10판 | PDF 3권, 항목 건수 미공개 | 해당 판의 파일별 이용 조건이 확인되지 않음. 제외 | [법제처 자료실](https://moleg.go.kr/board.es?act=view&bid=0001&list_no=146407&mid=a10108030000&nPage=1), [공공데이터포털 자료](https://www.data.go.kr/data/15105160/fileData.do) |
| 행정안전부 행정용어 순화어 참고자료 | HWP, 약 600개(게시글 표현) | 게시물에 재이용·변경 허락 표시가 확인되지 않음. 제외 | [행정안전부 게시물](https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000015&nttId=39969) |
| 서울시 행정순화어 | XLS, 461개(첨부 제목) | 첨부 파일 라이선스가 확인되지 않음. 제외 | [서울시 게시물](https://news.seoul.go.kr/gov/archives/510499) |

다듬은 말, 행정안전부, 서울시 자료는 목록의 존재와 건수를 조사했지만 재배포·변경 조건이 분명하지 않아 학습·평가 사전에 넣지 않았다. 법령 정비용어·일상용어 파일은 건수가 많아도 제4유형이므로 사용하지 않는다. API “제한 없음”은 데이터포털에 표시된 허용 범위 판단이며, 운영 단계 활용은 법제처 API 정책에 따른다.

## 사전 형태와 규칙

학습 도구는 `{어려운 말: {"alternatives": [쉬운 말...], "sources": [출처...]}}`를 사용한다. 국립국어원 이표기는 같은 대안어를 가진 별도 검색어로 넣고, 같은 어려운 말의 대안어와 출처는 중복 없이 합친다. 유니코드 NFC와 앞뒤 공백·인용부호를 정리한다. 한 글자 용어와 `가능`, `내용`, `대상`, `사항`처럼 지나치게 일반적인 용어는 제외한다. 서빙 모듈은 바꾸지 않았다.

국립국어원 원본은 기존처럼 자동으로 `data/nikl_terms.csv`에 받는다. 법제처 연계 응답은 `data/law_terms.xml`에 저장하면 로더가 함께 읽는다. 원본 자료는 `.gitignore` 대상이며 커밋하지 않는다. 법제처 API는 `OC` 인증값을 요구하고 전체 용어 일괄 다운로드 경로/전체 건수를 공개하지 않아, 등록한 API 활용 범위에 따라 연계 응답을 보관해야 한다.

## 데이터 적용 범위

측정 코드는 다음 명령으로 실제 파일을 읽어 문장 포함률과 출처별 용어 적중 수를 낸다.

```bash
python -m training.terms --data data --pairs data/pairs.jsonl --candidates data/eval/candidates.jsonl
```

이 작업 환경에는 `.gitignore` 처리된 `data/pairs.jsonl`, `data/eval/candidates.jsonl`과 두 출처 원본이 없었다. 따라서 통과 2,053짝의 원문 문장 비율, 출처별 적중 건수, 평가 후보 200건의 포함 건수는 측정하지 못했다. 값은 데이터 파일을 복구한 뒤 위 명령으로 산출해야 하며 현재 기록에는 추정치를 넣지 않았다. 계수는 “용어-문장 출현” 기준이어서 한 문장에 여러 용어가 나오면 출처별 건수가 각각 증가한다.

## 출처 링크

- [국립국어원 다듬은 말 항목 예시](https://www.korean.go.kr/front/imprv/refineView.do?imprv_refine_seq=504&mn_id=158)
- [국립국어원 우리말 다듬기 연혁 및 자료 설명](https://www.korean.go.kr/niklintro2/20years05_05_01.jsp)
- [법제처 법령용어-일상용어 연계 API 안내](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lstrmRltGuide)
- [법제처 일상용어-법령용어 연계 API 안내](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=dlytrmRltGuide)
