# CultureBridge

한국·중국·일본의 문화유산을 공식 자료에 근거해 비교하고, 학습 수준에 맞는 설명과 퀴즈를 제공하는 AI Agent 기반 교육 플랫폼입니다.

## 1. 현재 구현 범위

- 문화유산 목록·상세 조회 API
- 선택 문화유산을 기준으로 한 비교 후보 추천
- 두 문화유산의 구조·재료·시대·종교적 배경 비교
- 초급·중급·고급 학습 수준 선택
- 수준별 비교 해설·학습 목표·퀴즈: 초급 관찰, 중급 비교, 고급 근거 판단
- 네 역할의 Agent 흐름 골격
- 4개 Agent의 탐구 실행 API
- 공식 출처 범위 안에서 답하는 자유 질문 화면과 API
- 역사적 주장 검증 화면·API: 재료·시대·구조의 단일 사실 대조와 근거 표시
- 비교 결과·출처 스냅샷 SQLite 저장, 저장된 비교 목록과 다시 열기
- 5문항 퀴즈 화면·채점·해설과 SQLite 학습 기록
- NiceGUI 기반 웹 화면과 전용 키오스크 체험 흐름
- 키오스크용 대형 터치 버튼·수동 초기화·5분 미사용 자동 초기화
- 잘못된 비교·퀴즈 주소의 복귀 안내, DB 실패 안내 및 API 503 응답
- 키보드 선택 버튼·포커스 표시·입력 이름·결과 알림 영역·모바일 세로 비교 배치
- 공식 출처와 검증 상태를 포함한 샘플 데이터

## 2. 실행 방법

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m culturebridge.main
```

브라우저에서 `http://127.0.0.1:8080`을 열면 됩니다. API 문서는 `/docs`에서 확인할 수 있습니다.
박물관형 터치 체험은 `http://127.0.0.1:8080/kiosk`에서 시작합니다.
저장된 비교는 `http://127.0.0.1:8080/comparisons`에서 확인합니다.
목록은 계정별 기록이 아닌 이 기기의 공용 비교 결과입니다. 질문 입력은 저장하지 않습니다.

이미 설치된 프로젝트는 다음 명령으로 점검하고 시연할 수 있습니다.

```powershell
.\scripts\run.ps1 -CheckOnly -Offline
.\scripts\check.ps1
.\scripts\run.ps1 -Offline
```

`-Offline`은 키 설정 여부와 관계없이 앱의 자동 Gemini 호출을 끕니다.
다른 포트는 `-Port 8081`로 지정합니다. 서버 실행 중에는 터미널을 유지합니다.
자세한 순서는 [실행·5분 시연 안내](docs/05_실행_시연_안내.md)를 참고하세요.

## 3. 프로젝트 구조

```text
src/culturebridge/
  agents/       LangGraph 기반 Agent 흐름
  api/          FastAPI 엔드포인트
  data/         검증된 개발용 샘플 데이터
  domain/       요청·응답 데이터 모델
  services/     검색·추천·비교 업무 규칙
  ui/           NiceGUI 화면
docs/           요구사항·아키텍처·DB/API 설계
tests/          핵심 서비스와 API 테스트
```

## 4. 데이터 원칙

- 공식 기관 자료를 우선합니다.
- 출처 제목·기관·URL·조회일을 함께 저장합니다.
- UNESCO 출처에는 요약과 자료 범위를 함께 표시합니다. 문화유산은 3건, 출처는 4건입니다.
- 확인되지 않은 내용은 사실처럼 단정하지 않습니다.
- 생성형 AI는 초안 작성에만 사용하며, 검증 상태를 별도로 표시합니다.
- 주장 검증은 등록된 요약 데이터와 대조합니다. 실시간 원문 검색은 아직 지원하지 않습니다.
- 예: `석굴암의 재료는 화강암이다`. 일치하면 확인됨, 불일치하면 추가 확인 필요,
  지원하지 않는 문장이나 영향·인과 관계는 근거 부족으로 표시합니다.

## 5. Gemini 연동 점검

로컬 `.env`의 `GEMINI_API_KEY`와 `GEMINI_MODEL`을 설정한 뒤 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m culturebridge.check_gemini
```

`success`는 실제 AI 응답 수신, `failed`는 호출 실패, `not_configured`는 키 미설정입니다.
실제 호출은 설정한 계정의 API를 사용합니다. AI 결과는 추가 확인 필요로 표시합니다.
앱은 호출 실패·빈 응답 시 로컬 답변으로 전환하며 요청 제한시간 기본값은 15초입니다.
이번 검증에서는 키가 없어 실제 호출은 하지 않았고 대체 응답과 자원 정리는 모의 테스트했습니다.

출처 확인: [석굴암 UNESCO](https://whc.unesco.org/en/list/736/),
[호류지 UNESCO](https://whc.unesco.org/en/list/660/),
[실크로드 UNESCO](https://whc.unesco.org/en/list/1442/),
[Google SDK](https://googleapis.github.io/python-genai/).
