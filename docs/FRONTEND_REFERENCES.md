# 프론트엔드 디자인 참고 및 색 접근성

21st.dev의 아래 12개 사례에서 상호작용과 정보 배치만 참고했다. React 코드는 복사하지 않았고, 기존 Vue 구성요소와 CSS 토큰으로 다시 구현했다. 라이선스 열은 21st.dev가 공개한 구성요소/원본 출처에 확인 가능한 범위만 기록한다. 확인할 수 없는 항목은 사용 허가로 간주하지 않는다.

| # | 참고 사례 및 반영 위치 | 출처·라이선스 확인 |
|---|---|---|
| 1 | [anubra266 파일 업로드·붙여넣기 안내](https://21st.dev/%40anubra266/components/file-upload-1/upload-with-paste) — `S1Intake` | Ark UI File Upload를 사용한다고 표시. [Ark UI 라이선스: MIT](https://github.com/chakra-ui/ark/blob/main/LICENSE). 디자인만 참고. |
| 2 | [OriginUI textarea 힌트](https://21st.dev/%40originui/components/textarea/textarea-with-hint) — `S1Intake` 글자 수·안내 | 21st.dev 페이지에서 원본 저장소/라이선스를 확인하지 못함. 코드 미사용. |
| 3 | [anubra266 진행 표시](https://21st.dev/%40anubra266/components/progress-1/linear-with-label-progress) — `ProgressMeter` 문장 진행 안내 | Ark UI Progress 사용으로 표시. [Ark UI 라이선스: MIT](https://github.com/chakra-ui/ark/blob/main/LICENSE). 실시간 문장 수 API가 없어 완료 전 정확한 `12/40` 수치는 표시하지 않음. |
| 4 | [adit-firdaus 단계 설명](https://21st.dev/%40adit-firdaus/components/steps/vertical-with-descriptions) — `C1Rail` 4단계 | 해당 항목의 원본 저장소와 라이선스를 확인하지 못함. 코드 미사용. |
| 5 | [serafimcloud 쓰기 도구](https://21st.dev/%40serafimcloud/components/edit-tool/write-tool) — `S4Result` 바뀐 문장 요약 | 해당 항목의 원본 저장소와 라이선스를 확인하지 못함. 코드 미사용. |
| 6 | [Halaska segmented control](https://21st.dev/%40halaska-studio/components/segmented-control/two-segments) — 업로드/붙여넣기 전환 | [Halaska UI 저장소](https://github.com/Halaska-Studio/ui) 표시에 따라 MIT. 동작은 기존 탭을 사용하며 움직임 감소 설정을 지원. |
| 7 | [sean0205 비활성 배지](https://21st.dev/%40sean0205/components/badge-2/disabled) — 원문 유지 배지 | 항목에 MIT License 표시. [원본 ReUI](https://reui.io/). 코드 미사용. |
| 8 | [shugar 인라인 의견](https://21st.dev/%40shugar/components/feedback/inline) — `S5FeedbackPanel` 엄지 투표 | 원본 저장소/라이선스 확인 불가. 코드 미사용. |
| 9 | [shugar 성공 토스트](https://21st.dev/%40shugar/components/toast/success) — 의견 전송 확인 | 원본 저장소/라이선스 확인 불가. 코드 미사용. 메시지를 자동으로 숨기지 않아 읽을 시간을 보장. |
| 10 | [cnippet-dev 빈 상태](https://21st.dev/%40cnippet-dev/components/cnippet-empty/bordered) — `S6History` | 21st.dev의 컴포넌트 계열에 MIT 표시. [Cnippet UI](https://ui.cnippet.dev/). 코드 미사용. |
| 11 | [robertlib 최근 결과 타임라인](https://21st.dev/%40robertlib/components/timeline/compact-sidebar) — `S6History` 문서명·문장 수·상대 시간 | 원본 저장소/라이선스 확인 불가. 코드 미사용. |
| 12 | [haydenbleasel 상태 표시](https://21st.dev/%40haydenbleasel/components/status/custom-styles-status) — `C11ModelServerState` 상태 점+문구 | [Kibo UI 저장소 라이선스: MIT](https://github.com/shadcnblocks/kibo/blob/main/license.md). 페이지가 이 원본을 가리키는 것으로 표시됨. 코드 미사용. |

## 색 토큰과 대비

컴포넌트의 색상은 `frontend/src/styles/tokens.css`의 잉크, 중립 회색, 성공·주의·오류 토큰과 변경 강조용 하이라이트 토큰만 사용한다. 상태는 점과 텍스트를 함께 표시하고, 비교 차이는 색상 외 밑줄과 스크린리더 문구도 제공한다. 아래 명암비는 WCAG 상대 휘도 공식으로 계산했으며 일반 텍스트 기준 4.5:1을 넘는다.

| 전경 / 배경 | 대비 | 적용 |
|---|---:|---|
| 잉크 `#111111` / 흰색 `#ffffff` | 18.88:1 | 기본 본문·강조 |
| 중립 `#46464d` / 흰색 `#ffffff` | 9.36:1 | 보조 본문·설명 |
| 잉크 `#111111` / 하이라이트 `#fff2b2` | 16.72:1 | 문서 보기에서 바뀐 말 |
| 성공 `#1f7a3d` / 흰색 `#ffffff` | 5.37:1 | 성공 상태 텍스트 |
| 주의 `#805000` / 흰색 `#ffffff` | 6.85:1 | 지연·주의 상태 텍스트 |
| 오류 `#c0261b` / 흰색 `#ffffff` | 5.94:1 | 오류 텍스트 |
| 성공 `#1f7a3d` / 성공 연한 배경 `#e7f3e9` | 4.71:1 | 성공 배지 |
| 주의 `#805000` / 주의 연한 배경 `#fff4d6` | 6.25:1 | 주의 배지 |
| 오류 `#c0261b` / 오류 연한 배경 `#fdeceb` | 5.20:1 | 오류 배지 |

빌드 단계의 `frontend/scripts/check-colors.mjs`가 토큰 파일 밖의 직접 색상값 사용을 차단한다.
