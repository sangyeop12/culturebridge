from fastapi import APIRouter, HTTPException, Path, Query

from culturebridge.agents.autonomous import AutonomousRequest, AutonomousResult, run_autonomous
from culturebridge.agents.quiz_agent import evaluate_learning_quiz
from culturebridge.agents.workflow import exploration_graph
from culturebridge.domain.models import (
    ClaimRequest,
    ClaimResult,
    ComparisonRequest,
    ComparisonResult,
    ExplorationRequest,
    ExplorationResult,
    HeritageDetail,
    HeritageSummary,
    LearningGoal,
    LearningLevel,
    QuestionAnswer,
    QuestionRequest,
    QuizAttemptRequest,
    QuizAttemptResult,
    QuizRequest,
    QuizResponse,
    RelatedHeritage,
    SavedComparison,
    SavedComparisonSummary,
    SourceRecord,
)
from culturebridge.domain.official_models import (
    OfficialDocument,
    OfficialLocation,
    OfficialSearchResult,
)
from culturebridge.services.catalog_service import (
    HeritageNotFoundError,
    get_heritage,
    get_sources,
    list_heritages,
    recommend_related,
)
from culturebridge.services.claim_service import verify_claim
from culturebridge.services.comparison_service import (
    ComparisonNotFoundError,
    create_saved_comparison,
    get_saved_comparison,
    list_saved_comparisons,
)
from culturebridge.services.evidence_quiz_service import EvidenceQuizError
from culturebridge.services.home_search_service import (
    HomeSearchResult,
    HomeSuggestion,
    SearchScope,
    get_home_suggestions,
    search_home,
)
from culturebridge.services.lesson_service import HeritageLesson, explain_source, official_source
from culturebridge.services.location_service import get_official_location
from culturebridge.services.official_service import (
    OfficialDocumentNotFoundError,
    OfficialServiceError,
    get_official_document,
    search_official_heritages,
)
from culturebridge.services.question_service import answer_question
from culturebridge.services.quiz_service import (
    InvalidQuizAttemptError,
    QuizNotFoundError,
    generate_quiz,
)
from culturebridge.services.source_claim_service import ClaimTargetMismatchError
from culturebridge.services.unesco_service import (
    UnescoResult,
    UnescoSuggestion,
    get_unesco_suggestions,
    search_unesco,
)

router = APIRouter(prefix="/api", tags=["CultureBridge"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "CultureBridge"}


@router.post("/autonomous-explorations", response_model=AutonomousResult)
def autonomous_exploration(request: AutonomousRequest):
    try:
        return run_autonomous(request)
    except OfficialServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (ValueError, HeritageNotFoundError) as exc:
        raise HTTPException(
            status_code=422, detail="선택 대상 또는 탐구 자료를 확인하지 못했습니다."
        ) from exc


@router.get("/search", response_model=HomeSearchResult)
def home_search(
    q: str = Query(min_length=1, max_length=100),
    scope: SearchScope = "all",
    page: int = Query(default=1, ge=1, le=10000),
):
    try:
        return search_home(q, scope, page)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/search/suggestions", response_model=list[HomeSuggestion])
def home_suggestions(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=8, ge=1, le=20),
    scope: SearchScope = "all",
):
    return get_home_suggestions(q, limit, scope)


@router.get("/unesco/heritages", response_model=UnescoResult)
def unesco_heritages(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
):
    try:
        return search_unesco(q, limit, offset)
    except OfficialServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/unesco/suggestions", response_model=list[UnescoSuggestion])
def unesco_suggestions(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=8, ge=1, le=20),
):
    try:
        return get_unesco_suggestions(q, limit)
    except OfficialServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/official/heritages", response_model=OfficialSearchResult)
def official_search(
    q: str = Query(min_length=1, max_length=100),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=10, ge=1, le=50),
):
    try:
        return search_official_heritages(q, page, page_size)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OfficialServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/official/heritages/{kind}/{number}/{region}", response_model=OfficialDocument)
def official_detail(
    kind: str = Path(pattern=r"^\d{2}$"),
    number: str = Path(pattern=r"^\d{1,20}$"),
    region: str = Path(pattern=r"^\d{2}$"),
):
    try:
        return get_official_document(kind, number, region)
    except OfficialDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="공식 자료를 찾을 수 없습니다.") from exc
    except OfficialServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/heritages", response_model=list[HeritageSummary])
def heritages(q: str | None = Query(default=None, max_length=100)):
    return list_heritages(q)


@router.get("/official/heritages/{kind}/{number}/{region}/lesson", response_model=HeritageLesson)
def official_lesson(
    kind: str = Path(pattern=r"^\d{2}$"),
    number: str = Path(pattern=r"^\d{1,20}$"),
    region: str = Path(pattern=r"^\d{2}$"),
    level: LearningLevel = LearningLevel.BEGINNER,
):
    document = official_detail(kind, number, region)
    return explain_source(official_source(document), level)


@router.get(
    "/official/heritages/{kind}/{number}/{region}/location", response_model=OfficialLocation
)
def official_location(
    kind: str = Path(pattern=r"^\d{2}$"),
    number: str = Path(pattern=r"^\d{1,20}$"),
    region: str = Path(pattern=r"^\d{2}$"),
):
    try:
        return get_official_location(kind, number, region)
    except OfficialDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="일치하는 공식 위치 자료가 없습니다.") from exc
    except OfficialServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/heritages/{heritage_id}", response_model=HeritageDetail)
def heritage_detail(heritage_id: str):
    try:
        return get_heritage(heritage_id)
    except HeritageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="문화유산을 찾을 수 없습니다.") from exc


@router.get("/heritages/{heritage_id}/sources", response_model=list[SourceRecord])
def heritage_sources(heritage_id: str):
    try:
        item = get_heritage(heritage_id)
    except HeritageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="문화유산을 찾을 수 없습니다.") from exc
    return get_sources(item.source_ids)


@router.get("/heritages/{heritage_id}/related", response_model=list[RelatedHeritage])
def related_heritages(heritage_id: str, goal: LearningGoal = LearningGoal.COMPARE):
    try:
        return recommend_related(heritage_id, goal)
    except HeritageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="문화유산을 찾을 수 없습니다.") from exc


@router.post("/comparisons", response_model=ComparisonResult)
def create_comparison(request: ComparisonRequest):
    try:
        return create_saved_comparison(request.left_id, request.right_id, request.level)
    except HeritageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="비교할 문화유산을 찾을 수 없습니다.") from exc


@router.get("/comparisons", response_model=list[SavedComparisonSummary])
def comparison_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return list_saved_comparisons(limit, offset)


@router.get("/comparisons/{record_id}", response_model=SavedComparison)
def saved_comparison(record_id: str):
    try:
        return get_saved_comparison(record_id)
    except ComparisonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="저장된 비교를 찾을 수 없습니다.") from exc


@router.post("/explorations", response_model=ExplorationResult)
def create_exploration(request: ExplorationRequest):
    state = {
        "heritage_id": request.heritage_id,
        "level": request.level.value,
        "goal": request.goal.value,
        "goal_text": request.goal_text,
        "amount": request.amount.value,
    }
    if request.comparison_id:
        state["comparison_id"] = request.comparison_id
    try:
        result = exploration_graph.invoke(state)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeritageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="탐구할 문화유산을 찾을 수 없습니다.") from exc
    return ExplorationResult(
        heritage_id=request.heritage_id,
        comparison_id=result["comparison_id"],
        level=result["level"],
        curriculum=result["curriculum"],
        candidates=result["candidates"],
        comparison=result["comparison"],
        verification_status=result["verification_status"],
        verification_note=result["verification_note"],
        collected_sources=result["collected_sources"],
        extracted_fields=result["extracted_fields"],
        goal=result["goal"],
        goal_text=request.goal_text,
        amount=result["amount"],
        retry_count=result["retry_count"],
        execution_trace=result["execution_trace"],
        quiz=result["quiz"],
        quiz_notice=result["quiz_notice"],
    )


@router.post("/questions", response_model=QuestionAnswer)
def ask_question(request: QuestionRequest):
    try:
        return answer_question(
            request.left_id,
            request.right_id,
            request.question,
            request.level,
            comparison_id=request.comparison_id,
        )
    except ComparisonNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="질문의 비교 저장본을 찾을 수 없습니다."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeritageNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="질문에 사용할 문화유산을 찾을 수 없습니다."
        ) from exc


@router.post("/claims/verify", response_model=ClaimResult)
def check_claim(request: ClaimRequest):
    try:
        return verify_claim(
            request.left_id, request.right_id, request.claim, comparison_id=request.comparison_id
        )
    except ComparisonNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="검증할 비교 저장본을 찾을 수 없습니다."
        ) from exc
    except ClaimTargetMismatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeritageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="검증할 문화유산을 찾을 수 없습니다.") from exc


@router.post("/quizzes", response_model=QuizResponse)
def create_quiz(request: QuizRequest):
    try:
        return generate_quiz(
            request.left_id, request.right_id, request.level, comparison_id=request.comparison_id
        )
    except ComparisonNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="퀴즈의 저장된 비교를 찾을 수 없습니다."
        ) from exc
    except EvidenceQuizError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeritageNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="퀴즈에 사용할 문화유산을 찾을 수 없습니다."
        ) from exc


@router.post("/quiz-attempts", response_model=QuizAttemptResult)
def submit_quiz(request: QuizAttemptRequest):
    try:
        return evaluate_learning_quiz(request.quiz_id, request.answers)
    except QuizNotFoundError as exc:
        raise HTTPException(status_code=404, detail="퀴즈를 찾을 수 없습니다.") from exc
    except InvalidQuizAttemptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
