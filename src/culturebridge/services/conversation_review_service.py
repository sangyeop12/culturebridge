"""Import only owned graded records. A wrong answer is not an understanding assessment."""

from pydantic import ValidationError

from culturebridge.domain.learning import ConversationMessage
from culturebridge.domain.models import QuizAttemptResult, VerificationStatus
from culturebridge.services.operation_service import owner_key


class ReviewNotFoundError(KeyError):
    pass


def owned_review(connection, history_id):
    row = connection.execute(
        "SELECT r.result_json,r.quiz_id,h.score,h.total FROM learning_reviews r "
        "JOIN learning_history h ON h.id=r.history_id WHERE r.history_id=? AND r.owner=?",
        (history_id, owner_key()),
    ).fetchone()
    if row is None:
        raise ReviewNotFoundError(history_id)
    try:
        result = QuizAttemptResult.model_validate_json(row["result_json"])
    except ValidationError as exc:
        raise ValueError("이전 형식의 기록이에요. 기존 해설 화면에서 다시 살펴봐 주세요.") from exc
    if (
        result.quiz_id != row["quiz_id"]
        or not 0 <= row["score"] <= row["total"] <= 5
        or result.score != row["score"]
        or result.total != row["total"]
        or result.history_id not in {None, history_id}
    ):
        raise ValueError("채점 기록을 확인할 수 없어요. 기존 해설에서 확인해 주세요.")
    return result, row["score"], row["total"]


def seed_review(state, history_id, result, score, total):
    items, sources, seen = [], [], set()
    for item in result.review_items[: total - score]:
        if (
            not 1 <= item.number <= total
            or item.number in seen
            or item.selected == item.correct_answer
        ):
            continue
        seen.add(item.number)
        matches = [
            field
            for field in result.evidence
            if (
                field.evidence_quote == item.quote
                and item.quote
                and len(item.quote) <= 700
                and field.source_url
                and item.source_url
                and str(field.source_url) == str(item.source_url)
                and field.value
                and field.verification_status != VerificationStatus.INSUFFICIENT_EVIDENCE
            )
        ]
        unique = {(f.heritage_id, f.category, str(f.source_url)) for f in matches}
        matched = matches[0] if len(unique) == 1 else None
        source_id = f"quiz-review:{history_id}:{item.number}" if matched else ""
        entry = {
            "number": item.number,
            "question": item.question[:300],
            "selected": item.selected[:160],
            "correct_answer": item.correct_answer[:160],
            "activity": item.activity[:240],
            "source_id": source_id,
            "concept": matched.category if matched else "",
        }
        items.append(entry)
        if matched:
            sources.append(
                {
                    "id": source_id,
                    "name": "퀴즈 채점에 사용한 원문 근거",
                    "url": str(matched.source_url),
                    "reading_url": str(matched.source_url),
                    "excerpts": [{"concept": matched.category, "quote": item.quote}],
                }
            )
    state.quiz_review = {
        "history_id": history_id,
        "quiz_id": result.quiz_id,
        "score": score,
        "total": total,
        "items": items,
    }
    state.sources = sources
    state.goal = "퀴즈에서 고른 답을 원문과 함께 다시 설명하기"
    state.messages = [
        ConversationMessage(role="user", text="퀴즈에서 배운 내용을 다시 살펴볼게요.")
    ]
    if items:
        select_review_question(state, str(items[0]["number"]), initial=True)
    else:
        state.messages.append(
            ConversationMessage(
                role="assistant",
                text=(
                    "모든 문항을 맞혔어요. 한 번의 정답으로 이해도를 확정하지는 않아요. "
                    "기억에 남는 내용을 자기 말로 들려주세요."
                    if score == total and total > 0
                    else "이 기록에는 대화로 가져올 문항별 근거가 없어요. 기존 해설을 다시 읽거나 "
                    "궁금한 점을 들려주세요."
                ),
                suggestions=[{"label": "퀴즈 해설 다시 보기", "url": "/learning-history"}],
            )
        )


def select_review_question(state, number, *, initial=False):
    item = next((i for i in state.quiz_review.get("items", []) if str(i["number"]) == number), None)
    if item is None:
        raise ValueError("이 복습 대화에 있는 문항을 골라주세요.")
    source = next((s for s in state.sources if s["id"] == item["source_id"]), None)
    state.quiz_review["current_number"] = item["number"]
    state.checkpoint = {}
    if not initial:
        state.messages.append(
            ConversationMessage(role="user", text=f"{item['number']}번 다시 살펴보기")
        )
    text = (
        f"{item['number']}번 · {item['question']}\n\n"
        f"내가 고른 답: {item['selected']}\n채점된 정답: {item['correct_answer']}\n\n"
        "틀린 답 하나로 이해도를 단정하지 않아요. "
    )
    citations = []
    if source:
        quote = source["excerpts"][0]["quote"]
        question = "원문에서 근거가 되는 표현을 찾고, 왜 그렇게 생각하는지 자기 말로 설명해 볼까요?"
        text += f"저장된 채점 근거를 함께 읽어봐요.\n\n공식 원문: {quote}\n\n{question}"
        state.checkpoint = {
            "concept": item["concept"],
            "source_id": source["id"],
            "quote": quote,
            "question": question,
            "history_id": state.quiz_review["history_id"],
            "question_number": item["number"],
        }
        citations = [
            {
                "source_id": source["id"],
                "title": source["name"],
                "url": source["url"],
                "quote": quote,
            }
        ]
    else:
        text += "이 문항은 평가에 연결할 원문 근거가 부족해요. 기존 해설에서 다시 확인해 주세요."
    state.messages.append(
        ConversationMessage(
            role="assistant",
            text=text,
            citations=citations,
            suggestions=[{"label": "퀴즈 해설 다시 보기", "url": "/learning-history"}],
        )
    )
    state.plan_history.append(
        {"action": "quiz_review", "reason": "학습자가 선택한 퀴즈 문항을 원문과 다시 설명하기"}
    )
    state.notice = (
        "저장된 채점 근거를 사용해요. 현재 원문과 역사적 의미는 추가 확인이 필요할 수 있어요."
    )
