from fastapi import APIRouter, HTTPException, Query

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
from culturebridge.services.question_service import answer_question
from culturebridge.services.quiz_service import (
    InvalidQuizAttemptError,
    QuizNotFoundError,
    generate_quiz,
    grade_quiz,
)

router = APIRouter(prefix="/api", tags=["CultureBridge"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "CultureBridge"}


@router.get("/heritages", response_model=list[HeritageSummary])
def heritages(q: str | None = Query(default=None, max_length=100)):
    return list_heritages(q)


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
def related_heritages(heritage_id: str):
    try:
        return recommend_related(heritage_id)
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
    }
    if request.comparison_id:
        state["comparison_id"] = request.comparison_id
    try:
        result = exploration_graph.invoke(state)
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
    )


@router.post("/questions", response_model=QuestionAnswer)
def ask_question(request: QuestionRequest):
    try:
        return answer_question(
            request.left_id,
            request.right_id,
            request.question,
            request.level,
        )
    except HeritageNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="질문에 사용할 문화유산을 찾을 수 없습니다."
        ) from exc


@router.post("/claims/verify", response_model=ClaimResult)
def check_claim(request: ClaimRequest):
    try:
        return verify_claim(request.left_id, request.right_id, request.claim)
    except HeritageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="검증할 문화유산을 찾을 수 없습니다.") from exc


@router.post("/quizzes", response_model=QuizResponse)
def create_quiz(request: QuizRequest):
    try:
        return generate_quiz(request.left_id, request.right_id, request.level)
    except HeritageNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="퀴즈에 사용할 문화유산을 찾을 수 없습니다."
        ) from exc


@router.post("/quiz-attempts", response_model=QuizAttemptResult)
def submit_quiz(request: QuizAttemptRequest):
    try:
        return grade_quiz(request.quiz_id, request.answers)
    except QuizNotFoundError as exc:
        raise HTTPException(status_code=404, detail="퀴즈를 찾을 수 없습니다.") from exc
    except InvalidQuizAttemptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
