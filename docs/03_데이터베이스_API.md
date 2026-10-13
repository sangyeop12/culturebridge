# 4. 데이터베이스 및 API 개요

□ 4.1 데이터베이스 구성

| 테이블 | PK | 역할 |
| --- | --- | --- |
| heritages | id | 국가별 문화유산 기본 정보 |
| sources | id | 공식 자료와 출처 메타데이터 |
| comparisons | id | 문화유산 비교 분석 결과 |
| quiz_items | id | 학습 내용과 연결된 문제 |
| learning_history | id | 임시 세션과 퀴즈 결과 |
| official_documents | id | 국가유산청 상세 원문·정규화 내용·출처·조회 시각 캐시 |
| official_location_feeds | kind_code | 공간정보 API 종목별 XML·조회 시각 캐시 |
| unesco_feeds | language | UNESCO 영문 JSON 또는 XML·출처·이용 조건·조회 시각 캐시 |

□ 4.2 핵심 필드

- heritages: id·name·country·period·location·structure·material·religious_context·summary
- sources: id·heritage_id·title·organization·url·retrieved_at·license_note
- comparisons: id·left_id·right_id·level·content·verification_status
- quiz_items: id·comparison_id·level·question·choices·correct_index·explanation
- learning_history: id·session_id·heritage_id·level·score·created_at

□ 4.3 API 기능 구성

| 기능 | API |
| --- | --- |
| 상태 확인 | GET /api/health |
| 문화유산 목록·검색 | GET /api/heritages |
| 공식 API 검색 | GET /api/official/heritages?q=석굴암 |
| 공식 API 상세·캐시 | GET /api/official/heritages/{kind}/{number}/{region} |
| 공식 위치정보 | GET /api/official/heritages/{kind}/{number}/{region}/location |
| UNESCO 목록 검색 | GET /api/unesco/heritages?q=Japan&limit=20&offset=0 |
| 문화유산 상세 | GET /api/heritages/{id} |
| 비교 후보 추천 | GET /api/heritages/{id}/related |
| 문화유산 비교 | POST /api/comparisons |
| 저장된 비교 목록 | GET /api/comparisons?limit=20&offset=0 |
| 저장된 비교 상세 | GET /api/comparisons/{record_id} |
| Agent 탐구 실행 | POST /api/explorations |
| 출처 기반 자유 질문 | POST /api/questions |
| 역사적 주장 검증 | POST /api/claims/verify |
| 퀴즈 생성 | POST /api/quizzes |
| 퀴즈 답안 제출 | POST /api/quiz-attempts |

□ 4.4 공통 응답 원칙

- 존재하지 않는 ID는 HTTP 404로 반환한다.
- 잘못된 학습 수준과 답안은 HTTP 422로 반환한다.
- 비교 결과에는 공통점·차이점·출처·검증 상태를 포함한다.
- 오류 응답에는 사용자가 다음 행동을 선택할 수 있는 메시지를 포함한다.

□ 4.5 주장 검증 범위

- 요청: left_id·right_id·claim (2~500글자). 서로 다른 문화유산을 선택한다.
- 응답: claim·verification_status·explanation·evidence·sources·scope_note.
- 선택한 문화유산의 재료·시대·구조에 관한 단일 문장을 등록된 사실과 대조한다.
- 정확한 일치는 확인됨, 표현 불일치는 추가 확인 필요로 분류한다.
- 영향 관계·인과관계·복합 문장·지원하지 않는 문장은 근거 부족으로 분류한다.
- 원문 실시간 검색 및 자동 의미 판정은 향후 확장 범위다.

□ 4.6 비교 저장 및 재조회

- 비교 생성·웹 비교·키오스크 비교·Agent 탐구에서 UUID를 부여하고 SQLite에 저장한다.
- 저장 내용은 비교 전체·학습 수준·검증 상태·출처 메타데이터·UTC 생성 시각이다.
- 비교 응답의 saved_id로 저장 상세를 조회한다. 목록은 최신순이며 limit은 1~100이다.
- 웹 /comparisons에서 저장된 결과를 선택하면 당시 내용과 출처를 표시한다.
- 재조회는 기록을 추가하지 않는다. 새 비교 실행은 별도 기록을 생성한다.
- 계정이 없는 기기 공용 기록이며 질문·주장·개인정보는 비교 기록에 저장하지 않는다.

□ 4.7 공식 API 연동

- 국가유산청 XML을 서버에서 요청하며 serviceKey는 사용하지 않는다.
- 검색은 ccbaMnm1·pageIndex·pageUnit, 상세는 ccbaKdcd·ccbaAsno·ccbaCtcd를 전달한다.
- 번호를 문자열로 보관해 앞자리 0을 유지한다. XML 엔티티 확장은 차단한다.
- 상세 원문을 24시간 캐시하고, 만료 시 조회 실패하면 stale=true로 이전 자료를 안내한다.
- 검색·미수집 상세의 외부 장애는 502, 잘못된 코드는 422, 없는 상세는 404로 안내한다.
- 검색 UI는 첫 10건을 표시하며 API는 page·page_size로 페이지 조회를 지원한다.
- 수집된 석굴암의 최신 본문을 Gemini 질문 근거로 전달하고 출처 링크를 반환한다.
- 기존 비교·퀴즈·단일 주장 대조의 구조화 자료를 자동 덮어쓰지 않는다.

□ 4.8 공간정보 API 연동

- gis-heritage.go.kr/openapi/xmlService/spca.do에 ccbaKdcd를 전달한다.
- 종목별 응답에서 유산명·지정종목·시군구로 대조하며 모호한 후보를 선택하지 않는다.
- projected_x·projected_y는 UTM-K 원좌표, latitude·longitude는 상세 API의 별도 좌표다.
- 응답에 두 출처 URL·조회 시각·cached·stale을 포함한다.
- 공식 상세 화면의 버튼으로 조회한다. 외부 지도 링크는 유효한 위도·경도가 있을 때 제공한다.
- 지도 경계 레이어·좌표 변환은 포함하지 않는다.

□ 4.9 UNESCO XML

- 영문 XML의 query/row와 id_number·site·states·date_inscribed를 파싱한다.
- 출처 URL은 검증된 숫자 ID로 UNESCO 공식 개별 페이지를 구성한다.
- 10MB 제한 및 XML 엔티티 차단, 원문 로컬 저장 및 24시간 캐시를 적용한다.
- 미수집 상태의 외부 장애는 502, 오래된 캐시로 대체하면 stale=true를 반환한다.
- 현재 실서버의 공식 요청은 403이며 사용자 다운로드 파일의 로컬 가져오기를 지원한다.
- 본문 번역·요약·Gemini 근거 연결은 하지 않는다. 이용 조건과 출처를 표시한다.

□ 4.10 UNESCO 자동 갱신 경로 보완

- XML 서버의 Cloudflare 403을 확인하고 공식 DataHub whc001 JSON API로 기본 수집을 전환했다.
- 요청: /api/explore/v2.1/catalog/datasets/whc001/exports/json.
- select=id_no,name_en,states_names,date_inscribed로 필요한 네 필드만 수집한다.
- format·source_url·license_url 컬럼을 기존 캐시에 추가한다. 이전 XML은 그대로 호환된다.
- 만료 캐시 조회 또는 UI 공식 데이터 새로고침으로 수집한다. 실패하면 기존 자료를 보관한다.
- 실제 DataHub 응답 HTTP 200과 1,273건 갱신을 확인했다. 데이터셋 라이선스는 CC BY-SA 4.0이다.

□ 4.11 한글 검색 매칭 및 자동완성

- 한글 유산 별칭은 공식 등재 ID, 한·중·일 국가명은 정확한 국가 항목과 대조한다.
- 대안탑 별칭은 실크로드 유산군 ID 1442에 연결하며 독립 등재로 표시하지 않는다.
- 공식 원문 이름은 유지한다. 현재 한글 별칭 지원 범위는 README에 명시한다.
- GET /api/unesco/suggestions?q=호&limit=8은 로컬 캐시만 사용한다. limit 범위는 1~20이다.
- 화면은 입력 중 최대 8개의 선택 가능한 버튼을 제안하고 Enter 검색·Tab 완성을 지원한다.

□ 4.12 Agent 공식 자료 수집

- POST /api/explorations의 역사 탐구 Agent가 양쪽 유산의 수집 서비스를 실행한다.
- 응답 및 저장된 비교의 collected_sources에 본문·출처·조회일·범위·상태를 포함한다.
- 상태는 fresh·cached·stale·unavailable이며 실패한 자료의 본문을 생성하지 않는다.
- 미수집·만료 자료가 있으면 탐구 전체의 verification_status는 needs_review다.
- 구조화 비교·퀴즈의 기존 사실 데이터는 유지한다. 수집 결과를 사실 검증 완료로 간주하지 않는다.

□ 4.13 항목 추출·근거

- DataHub JSON 수집 필드에 short_description_en을 추가한다. 영문 소개를 본문으로 보관한다.
- CollectedSource의 content_kind는 individual_text·group_text·metadata를 구분한다.
- comparison_agent는 유효한 individual_text에서 두 유산의 시대·구조·재료를 추출한다.
- 응답 및 저장된 비교의 extracted_fields에 값·출처·원문 인용·방식·상태를 기록한다.
- Gemini JSON 스키마와 길이 제한을 적용하고 인용·유산 연결을 코드에서 재검사한다.
- 근거 없음은 insufficient_evidence, 원문 인용이 존재하는 후보는 needs_review다.
- 실패 시 로컬 문장 탐색으로 전환한다. 의미 대조 및 검증 완료로의 승격은 하지 않는다.

□ 4.14 근거 기반 비교·퀴즈

- 비교의 basis는 curated·extracted를 구분한다. extracted 비교에는 세 항목과 항목별 출처 ID를 저장한다.
- 원문·유산·자료 범위를 다시 대조한 추출 후보만 사용하며 값이 없으면 근거 부족으로 표시한다.
- 퀴즈 요청의 comparison_id로 저장된 원문을 재사용한다. 수준별 5문항을 템플릿으로 구성한다.
- quiz_items에 comparison_id·evidence_json을 추가한다. 채점 후 evidence로 원문 근거를 반환한다.
- 근거 미제공 및 대상 불일치는 422, 저장 비교 미존재는 404다.
- 이전 비교·퀴즈와 호환되며 새 퀴즈가 과거 저장본을 수정하지 않는다.

□ 4.15 원문 기반 주장 검토

- ClaimRequest의 comparison_id로 선택한 비교 저장본을 사용한다.
- ClaimResult는 basis=official_snapshot, used_ai, assessment를 포함한다.
- assessment는 source_match·support_candidate·contradiction_candidate·mixed·insufficient다.
- evidence에 지지/반박/관련 관계, 주장 부분, 원문 인용, 출처를 반환한다.
- Gemini 분해·의미 판정은 검토 후보이며 코드에서 인용과 유산 연결을 재검사한다.
- 원문 일치 외에는 verified로 승격하지 않는다. 인용 없는 부분을 따로 안내한다.
- 원문이 오래되었거나 대상이 유산군·메타데이터이면 의미 대조 대상에서 제외한다.
- 비교 미존재는 404, 비교 대상 불일치는 422다. 사용자 주장은 저장하지 않는다.
