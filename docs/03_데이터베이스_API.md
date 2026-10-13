# 4. 데이터베이스 및 API 개요

□ 4.1 데이터베이스 구성

| 테이블 | PK | 역할 |
| --- | --- | --- |
| heritages | id | 국가별 문화유산 기본 정보 |
| sources | id | 공식 자료와 출처 메타데이터 |
| comparisons | id | 문화유산 비교 분석 결과 |
| quiz_items | id | 학습 내용과 연결된 문제 |
| learning_history | id | 임시 세션과 퀴즈 결과 |

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
