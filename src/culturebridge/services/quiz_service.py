import json
from uuid import uuid4

from culturebridge.database import (
    initialize_database,
    load_quiz_items,
    save_learning_result,
    save_quiz_items,
    transaction,
)
from culturebridge.domain.models import (
    ExtractedField,
    LearningLevel,
    QuizAttemptResult,
    QuizChoice,
    QuizItem,
    QuizResponse,
    QuizReviewItem,
)
from culturebridge.services.catalog_service import LEARNING_GOALS, get_heritage
from culturebridge.services.curriculum_service import GOAL_LABELS
from culturebridge.services.display_service import display_name, korean_name
from culturebridge.services.operation_service import owner_key, reused_operation


class QuizNotFoundError(KeyError):
    pass


class InvalidQuizAttemptError(ValueError):
    pass


def _choice_index(choices: list[str], answer: str) -> int:
    return choices.index(answer)


@reused_operation("quiz")
def generate_quiz(
    left_id: str,
    right_id: str,
    level: LearningLevel,
    *,
    comparison_id: str | None = None,
    reuse: bool = False,
) -> QuizResponse:
    left = get_heritage(left_id)
    right = get_heritage(right_id)
    initialize_database()
    if comparison_id:
        from culturebridge.services.evidence_quiz_service import generate_evidence_quiz

        if reuse:
            # Persistent, owner-scoped reuse survives the short request cache and restarts.
            from culturebridge.services.comparison_service import get_saved_comparison

            comparison = get_saved_comparison(comparison_id).comparison
            if (comparison.left.id, comparison.right.id) != (left_id, right_id):
                raise InvalidQuizAttemptError("퀴즈와 선택한 문화유산이 다릅니다.")
            with transaction() as connection:
                row = connection.execute(
                    "SELECT q.quiz_id FROM quiz_items q JOIN resource_owners o "
                    "ON o.kind='quiz' AND o.id=q.quiz_id "
                    "WHERE q.comparison_id=? AND q.level=? AND o.owner=? "
                    "ORDER BY q.rowid DESC LIMIT 1",
                    (comparison_id, level.value, owner_key()),
                ).fetchone()
            if row:
                return load_quiz(row["quiz_id"], left_id, right_id)
        return generate_evidence_quiz(left_id, right_id, level, comparison_id)
    if left_id.startswith(("khs:", "unesco:", "official:")) or right_id.startswith(
        ("khs:", "unesco:", "official:")
    ):
        from culturebridge.services.evidence_quiz_service import EvidenceQuizError

        raise EvidenceQuizError("새 공식 대상의 퀴즈는 Agent가 만든 근거 비교 저장본이 필요합니다.")
    quiz_id = uuid4().hex
    countries = ["대한민국", "일본", "중국", "해당 없음"]
    materials = ["화강암", "목재", "벽돌", "금속"]
    names = [left.name, right.name, "불국사", "해당 없음"]

    raw_items = [
        (
            f"{quiz_id}-1",
            f"{left.name}이 위치한 나라는 어디인가요?",
            countries,
            _choice_index(countries, left.country),
            f"{left.name}은(는) {left.country}에 있습니다.",
        ),
        (
            f"{quiz_id}-2",
            f"{right.name}의 주요 재료는 무엇인가요?",
            materials,
            _choice_index(materials, right.material),
            f"{right.name}의 주요 재료는 {right.material}입니다.",
        ),
        (
            f"{quiz_id}-3",
            f"'{left.structure}'이라는 설명에 해당하는 문화유산은 무엇인가요?",
            names,
            _choice_index(names, left.name),
            f"이 구조 설명은 {left.name}에 해당합니다.",
        ),
        (
            f"{quiz_id}-4",
            "두 문화유산을 함께 비교할 수 있는 공통 맥락은 무엇인가요?",
            ["동아시아 불교문화", "근대 산업화", "서양 고전주의", "해양 무역만의 역사"],
            0,
            "두 유산은 동아시아 불교문화의 전개라는 공통 맥락에서 비교할 수 있습니다.",
        ),
        (
            f"{quiz_id}-5",
            "AI의 역사 설명을 확인할 때 가장 먼저 해야 할 일은 무엇인가요?",
            ["공식 출처 확인", "문장 길이 비교", "화면 색상 변경", "결론부터 암기"],
            0,
            "역사 설명은 공식 출처와 근거 범위를 먼저 확인해야 합니다.",
        ),
    ]
    if level is LearningLevel.INTERMEDIATE:
        raw_items = [
            (
                f"{quiz_id}-1",
                "두 문화유산의 시대 정보가 올바르게 연결된 것은 무엇인가요?",
                [
                    f"{left.name}: {left.period} / {right.name}: {right.period}",
                    "두 유산 모두 20세기에 조성되었다",
                    "국가가 같으면 조성 시기도 반드시 같다",
                    "재료만으로 정확한 조성 연대를 확정할 수 있다",
                ],
                0,
                f"등록된 시대는 {left.name} {left.period}, {right.name} {right.period}입니다.",
            ),
            (
                f"{quiz_id}-2",
                "두 유산의 재료와 구조를 연결한 설명으로 올바른 것은 무엇인가요?",
                [
                    f"{left.name}: {left.material}·{left.structure}",
                    "재료가 다르면 종교적 맥락도 반드시 다르다",
                    "같은 종교의 건축물은 모두 같은 구조다",
                    "구조 설명만으로 모든 시공 원인을 확정할 수 있다",
                ],
                0,
                "재료와 구조는 함께 비교할 수 있지만 "
                "종교나 시공 원인을 자동으로 결정하지 않습니다.",
            ),
            (
                f"{quiz_id}-3",
                "두 유산의 공통점과 차이점을 함께 비교하는 방법은 무엇인가요?",
                [
                    "불교라는 공통 맥락과 지역별 구조·재료의 차이를 함께 살핀다",
                    "지역이 다르면 공통점은 없다고 결론 낸다",
                    "공통점이 있으면 모든 차이를 무시한다",
                    "국가 이름만으로 문화적 가치를 순위 매긴다",
                ],
                0,
                "공통 맥락과 개별 특징을 함께 살펴야 비교의 근거가 드러납니다.",
            ),
            (
                f"{quiz_id}-4",
                "시대가 비슷한 두 문화유산에 대해 타당한 판단은 무엇인가요?",
                [
                    "시기는 비교 단서이며 직접 교류 여부는 추가 근거가 필요하다",
                    "시대가 비슷하면 장인들이 반드시 만났다",
                    "시대가 비슷하면 한 유산이 다른 유산을 복제했다",
                    "같은 세기라면 모든 구조가 같다",
                ],
                0,
                "시간적 근접성과 실제 교류를 구분해야 합니다.",
            ),
            (
                f"{quiz_id}-5",
                "재료가 선택된 이유를 더 알아보려면 어떤 자료가 필요한가요?",
                [
                    "해당 유산의 환경·시공에 관한 추가 공식 자료",
                    "재료 이름만 반복한 문장",
                    "출처 없는 추측",
                    "다른 유산의 사진 한 장만",
                ],
                0,
                "재료라는 사실만으로 선택 원인은 확정되지 않습니다. 원인을 다룬 자료가 필요합니다.",
            ),
        ]
    elif level is LearningLevel.ADVANCED:
        raw_items = [
            (
                f"{quiz_id}-1",
                "등록된 자료에서 확인한 사실과 해석을 올바르게 구분한 것은 무엇인가요?",
                [
                    f"{left.name}의 재료 정보({left.material})와 선택 원인은 별도로 검토한다",
                    "재료가 같으면 동일한 장인이 만들었다고 확정한다",
                    "자료에 없는 설명도 AI가 말하면 확인된 사실로 취급한다",
                    "공식 자료 링크가 있으면 답변 전체가 검증되었다고 판단한다",
                ],
                0,
                "항목별 사실과 원인 해석의 근거를 분리해야 합니다. "
                "링크만으로 모든 주장이 입증되지는 않습니다.",
            ),
            (
                f"{quiz_id}-2",
                "구조가 비슷하므로 직접 기술 전파가 있었다는 주장에 필요한 검증은 무엇인가요?",
                [
                    "문헌·고고학 자료 등 독립된 근거를 추가 대조한다",
                    "유사성 하나만으로 전파를 확정한다",
                    "AI 답변을 여러 번 받아 다수결로 결정한다",
                    "현재 소개 자료에 없으므로 전파가 없었다고 확정한다",
                ],
                0,
                "유사성은 관찰이며 전파는 추가 근거가 필요한 주장입니다. "
                "자료 부재는 부정의 증명도 아닙니다.",
            ),
            (
                f"{quiz_id}-3",
                "현재 요약 데이터로 판단할 수 없는 장인들의 만남은 어떻게 표시해야 하나요?",
                ["근거 부족", "확인됨", "거짓으로 확정", "AI의 확신이 높으면 사실"],
                0,
                "판단할 자료가 부족하면 근거 부족으로 남겨야 하며 "
                "사실이나 거짓으로 확정하지 않습니다.",
            ),
            (
                f"{quiz_id}-4",
                "창건 연대와 재건 연대가 다를 수 있는 유산의 시대를 검토할 때 적절한 방법은?",
                [
                    "연대가 가리키는 사건과 원문의 범위를 확인한다",
                    "가장 오래된 숫자만 골라 모든 건물에 적용한다",
                    "요약의 세기 표시만으로 모든 부재의 연대를 확정한다",
                    "연대가 여러 개면 공식 자료 전체를 거짓으로 취급한다",
                ],
                0,
                "연대의 대상과 자료 범위를 구분해야 하며 "
                "현재 요약만으로 세부 연대는 확정할 수 없습니다.",
            ),
            (
                f"{quiz_id}-5",
                "AI 설명에 출처 링크가 연결되었지만 문장별 대조를 하지 않았다면 적절한 상태는?",
                ["추가 확인 필요", "무조건 확인됨", "무조건 거짓", "출처를 삭제하면 확인됨"],
                0,
                "출처 연결과 주장의 검증은 다릅니다. AI 초안은 출처와 문장별 대조가 필요합니다.",
            ),
        ]

    # Shuffle once, then persist the same choice ordering for resuming this quiz.
    from culturebridge.services.quiz_choice_service import answer_positions, arranged_choices

    rotated_items = []
    for position, (item_id, question, choices, correct_index, explanation) in zip(
        answer_positions(len(raw_items)), raw_items, strict=True
    ):
        rotated = arranged_choices(choices, correct_index, position)
        rotated_items.append((item_id, question, rotated, position, explanation))
    raw_items = rotated_items
    save_quiz_items(quiz_id, left.id, level.value, raw_items)
    items = [
        QuizItem(
            id=item_id,
            question=question,
            choices=[QuizChoice(id=index, text=text) for index, text in enumerate(choices)],
            correct_index=correct_index,
            explanation=explanation,
        )
        for item_id, question, choices, correct_index, explanation in raw_items
    ]
    return QuizResponse(
        quiz_id=quiz_id, level=level, learning_goal=LEARNING_GOALS[level], items=items
    )


@reused_operation("grade")
def grade_quiz(quiz_id: str, answers: list[int]) -> QuizAttemptResult:
    rows = load_quiz_items(quiz_id)
    if not rows:
        raise QuizNotFoundError(quiz_id)
    if len(answers) != len(rows):
        raise InvalidQuizAttemptError(f"답안은 {len(rows)}개를 제출해야 합니다.")
    if any(answer < 0 or answer > 3 for answer in answers):
        raise InvalidQuizAttemptError("각 답안은 0부터 3 사이여야 합니다.")

    score = 0
    explanations = []
    review_steps = []
    review_items = []
    for position, (row, answer) in enumerate(zip(rows, answers, strict=True), start=1):
        choices = json.loads(row["choices_json"])
        correct_index = row["correct_index"]
        is_correct = answer == correct_index
        score += int(is_correct)
        result_label = "정답" if is_correct else f"오답 · 정답: {choices[correct_index]}"
        explanations.append(f"{position}번 {result_label} · {row['explanation']}")
        if not is_correct:
            wrong = choices[answer]
            followup = (
                "등재 연도와 건립·재건 연대를 구분해 보세요."
                if "등재" in wrong
                else "어느 유산의 설명인지 이름과 인용 범위를 다시 확인하세요."
                if "유산" in wrong
                else "선택한 보기의 핵심 단어가 원문에 직접 나오는지 찾아보세요."
            )
            review_steps.append(
                f"{position}번 다시 보기: {row['question']} → 정답: {choices[correct_index]} · "
                f"{row['explanation']} · 보충 학습: {followup}"
            )
            evidence = json.loads(row["evidence_json"])
            identities = {field["heritage_id"] for field in evidence}
            named = set()
            for identity in identities:
                original = get_heritage(identity).name
                aliases = (
                    original,
                    display_name(identity, original),
                    korean_name(identity, original),
                )
                if any(name and name in row["question"] for name in aliases):
                    named.add(identity)
            if named:
                evidence = [field for field in evidence if field["heritage_id"] in named]
            matched = next(
                (
                    field
                    for field in evidence
                    if field.get("evidence_quote")
                    and field["evidence_quote"] in row["explanation"]
                    and field["category"] in row["explanation"]
                ),
                {},
            )
            matched = matched or next(
                (
                    field
                    for field in evidence
                    if field.get("value") == choices[correct_index]
                    or field.get("evidence_quote") == choices[correct_index]
                ),
                {},
            )
            if not matched:
                materials = {
                    "stone": "석재",
                    "granite": "화강암",
                    "wood": "목재",
                    "wooden": "목재",
                    "brick": "벽돌",
                }
                matched = next(
                    (
                        field
                        for field in evidence
                        if field.get("category") == "재료"
                        and materials.get(field.get("value", "").casefold())
                        == choices[correct_index]
                    ),
                    {},
                )
            if matched:
                followup = {
                    "시대": "원문에서 연도와 사건을 함께 표시하고, 건립·재건·추정을 구분해 보세요.",
                    "구조": "정답과 고른 보기가 같은 부분을 설명하는지 확인해요. "
                    "평면·지붕·봉분을 나누어 원문에서 찾아보세요.",
                    "재료": "원문의 재료 표현을 찾고, "
                    "다른 유산의 재료와 같은지 다른지 설명해 보세요.",
                    "종교적 배경": "종교 이름과 유산의 쓰임을 구분해 읽고, "
                    "원문에 있는 설명으로 답해 보세요.",
                }[matched["category"]]
            review_items.append(
                QuizReviewItem(
                    number=position,
                    question=row["question"],
                    selected=choices[answer],
                    correct_answer=choices[correct_index],
                    activity=(
                        f"‘{choices[answer]}’ 대신 ‘{choices[correct_index]}’인 이유를 "
                        "설명해 볼까요? "
                    )
                    + followup,
                    quote=matched.get("evidence_quote", ""),
                    source_url=matched.get("source_url"),
                )
            )

    history_id = save_learning_result(
        session_id=quiz_id,
        heritage_id=rows[0]["heritage_id"],
        level=rows[0]["level"],
        score=score,
        total=len(rows),
    )
    result = QuizAttemptResult(
        history_id=history_id,
        quiz_id=quiz_id,
        score=score,
        total=len(rows),
        explanations=explanations,
        review_steps=review_steps,
        review_items=review_items,
        evidence=[
            ExtractedField.model_validate(field) for field in json.loads(rows[0]["evidence_json"])
        ],
    )
    with transaction() as connection:
        connection.execute(
            "INSERT INTO learning_reviews VALUES(?,?,?,?)",
            (history_id, quiz_id, result.model_dump_json(), owner_key()),
        )
    return result


def load_quiz(quiz_id: str, left_id: str, right_id: str) -> QuizResponse:
    rows = load_quiz_items(quiz_id)
    if not rows:
        raise QuizNotFoundError(quiz_id)
    comparison_id = rows[0]["comparison_id"]
    if not comparison_id:
        raise InvalidQuizAttemptError("이 퀴즈는 Agent 탐구 저장본에 연결되지 않았습니다.")
    from culturebridge.services.comparison_service import get_saved_comparison

    saved = get_saved_comparison(comparison_id).comparison
    if (saved.left.id, saved.right.id) != (left_id, right_id):
        raise InvalidQuizAttemptError("퀴즈와 선택한 문화유산이 다릅니다.")
    with transaction() as connection:
        metadata = connection.execute(
            "SELECT generation_note FROM quiz_metadata WHERE quiz_id=?", (quiz_id,)
        ).fetchone()
    return QuizResponse(
        quiz_id=quiz_id,
        generation_note=metadata["generation_note"] if metadata else "",
        level=LearningLevel(rows[0]["level"]),
        learning_goal=GOAL_LABELS[saved.goal.value] + " · 공식 설명으로 배운 내용 확인",
        comparison_id=comparison_id,
        basis="extracted",
        verification_status=saved.verification_status,
        items=[
            QuizItem(
                id=row["id"],
                question=row["question"],
                correct_index=row["correct_index"],
                explanation=row["explanation"],
                choices=[
                    QuizChoice(id=i, text=text)
                    for i, text in enumerate(json.loads(row["choices_json"]))
                ],
            )
            for row in rows
        ],
    )
