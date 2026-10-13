from uuid import uuid4

from culturebridge.database import save_quiz_items
from culturebridge.domain.models import (
    LearningLevel,
    QuizChoice,
    QuizItem,
    QuizResponse,
    VerificationStatus,
)
from culturebridge.services.comparison_service import get_saved_comparison
from culturebridge.services.evidence_comparison_service import supported_fields


class EvidenceQuizError(ValueError):
    pass


def generate_evidence_quiz(left_id, right_id, level: LearningLevel, comparison_id: str):
    saved = get_saved_comparison(comparison_id)
    comparison = saved.comparison
    if (comparison.left.id, comparison.right.id) != (left_id, right_id):
        raise EvidenceQuizError("저장된 비교의 대상과 퀴즈 대상이 다릅니다.")
    fields = supported_fields(comparison)
    if not fields:
        raise EvidenceQuizError(
            "유효한 원문 근거가 없어 퀴즈를 만들 수 없습니다. 공식 자료 탐구를 다시 실행하세요."
        )
    first, second = fields[0], fields[1] if len(fields) > 1 else fields[0]
    names = {comparison.left.id: comparison.left.name, comparison.right.id: comparison.right.name}
    other_name = names[right_id if first.heritage_id == left_id else left_id]
    source = next(s for s in comparison.collected_sources if s.id == second.source_id)
    question_rows = {
        LearningLevel.BEGINNER: [
            (
                f"다음 수집 원문이 연결된 유산은?\n{first.evidence_quote}",
                [
                    names[first.heritage_id],
                    other_name,
                    "두 유산 모두로 연결됨",
                    "자료에 출처가 없음",
                ],
                "인용의 출처는 " + names[first.heritage_id] + "입니다.",
            ),
            (
                f"다음 원문의 수집 출처는?\n{second.evidence_quote}",
                [
                    source.organization + " · " + source.title,
                    "출처 없는 추측",
                    "사용자 댓글",
                    "자료에 출처가 없음",
                ],
                "저장된 공식 자료의 기관과 제목을 확인하세요.",
            ),
            (
                f"현재 {names[first.heritage_id]}의 {first.category} 추출 후보로 저장된 값은?",
                [
                    first.value,
                    "자료 없이 단정한 값",
                    "등재연도를 무조건 건립연도로 바꾼 값",
                    "추출 결과가 항상 최종 사실임",
                ],
                "정답은 저장된 추출 후보입니다. 역사적 사실의 최종 확정이라는 뜻은 아닙니다.",
            ),
            (
                "원문에 없는 항목은 어떻게 표시하나요?",
                ["근거 부족", "임의 추측", "무조건 확인됨", "자동으로 다른 유산 값을 복사"],
                "원문 근거가 없으면 값을 추정하지 않습니다.",
            ),
            (
                "이 추출 후보를 다시 확인하려면 무엇을 보나요?",
                ["연결된 원문 문장과 출처", "답변 글자 수", "화면 색상", "AI 확신만"],
                "원문과 값의 의미·범위를 함께 검토합니다.",
            ),
        ],
        LearningLevel.INTERMEDIATE: [
            (
                f"{names[first.heritage_id]}의 {first.category} 후보를 비교하는 타당한 방법은?",
                [
                    "각 유산의 같은 항목과 원문 범위를 대조한다",
                    "유산명이 다르면 모든 값이 다르다고 판단한다",
                    "등재연도를 건립연도로 사용한다",
                    "자료 없는 항목을 복사한다",
                ],
                "같은 비교 항목을 사용하고 근거의 범위를 확인해야 합니다.",
            ),
            (
                f"{names[second.heritage_id]}의 {second.category} 추출에서 연결된 원문은?",
                [
                    second.evidence_quote,
                    "이 항목은 아무 자료 없이 확정되었다",
                    "다른 유산의 값으로 자동 대체해야 한다",
                    "모든 시공 원인은 이미 확인되었다",
                ],
                "정답 문장은 해당 항목의 저장된 원문 인용입니다.",
            ),
            (
                "양쪽 자료에서 시대가 비슷해 보일 때 타당한 판단은?",
                [
                    "교류 여부는 추가 증거가 필요하다",
                    "장인들이 반드시 만났다",
                    "직접 복제를 확정한다",
                    "구조가 모두 같다고 확정한다",
                ],
                "시기와 교류의 증거를 분리합니다.",
            ),
            (
                "한쪽 구조 항목만 근거가 있을 때 해야 할 일은?",
                [
                    "다른 쪽은 근거 부족으로 남긴다",
                    "같은 구조로 채운다",
                    "다른 종교로 단정한다",
                    "AI가 설명하면 원문을 생략한다",
                ],
                "비교의 빈칸을 추측으로 채우지 않습니다.",
            ),
            (
                "추출한 재료명만으로 선택 원인을 알 수 있나요?",
                [
                    "원인을 다룬 추가 자료가 필요하다",
                    "재료명만으로 모두 알 수 있다",
                    "국가명만으로 확정할 수 있다",
                    "등재 ID로 원인을 확정한다",
                ],
                "재료 정보와 선택 원인은 별도의 주장입니다.",
            ),
        ],
        LearningLevel.ADVANCED: [
            (
                f"이 인용의 원문 일치를 확인한 경우 타당한 상태는?\n{first.evidence_quote}",
                [
                    "추출 의미는 추가 확인 필요",
                    "추출한 모든 해석까지 확인됨",
                    "원문을 보지 않아도 최종 사실",
                    "그 유산의 모든 주장이 거짓",
                ],
                "문자열 일치와 의미 검증은 다릅니다.",
            ),
            (
                "수집 내용이 등재명·등재연도뿐이라면 건립연도 추출에 사용할 수 있나요?",
                [
                    "사용할 수 없으며 개별 원문이 필요하다",
                    "등재연도와 건립연도는 같다",
                    "ID 숫자가 건립연도다",
                    "최신 조회일이 건립연도다",
                ],
                "메타데이터의 날짜와 유산의 역사 연대를 구분합니다.",
            ),
            (
                "유산군 전체 설명을 구성 유산 한 곳의 재료 근거로 사용해도 되나요?",
                [
                    "개별 유산 근거가 필요하다",
                    "그룹에 속하면 모두 같은 재료다",
                    "국가만 같으면 적용된다",
                    "출처 링크만 있으면 적용된다",
                ],
                "자료의 대상 범위가 일치해야 합니다.",
            ),
            (
                f"{names[second.heritage_id]}의 {second.category} 후보의 추적 가능한 근거는?",
                [
                    second.evidence_quote,
                    "모든 시대의 유산은 같은 구조다",
                    "자료가 오래돼도 조회일을 숨긴다",
                    "원문 대신 AI 확신을 근거로 삼는다",
                ],
                "저장된 인용과 그 출처로 돌아갈 수 있어야 합니다.",
            ),
            (
                "자료가 최신 캐시여도 직접 영향 관계를 주장하려면?",
                [
                    "독립된 추가 증거를 대조한다",
                    "캐시가 있으면 모든 관계가 입증된다",
                    "유사성만으로 확정한다",
                    "자료에 없으면 거짓으로 확정한다",
                ],
                "수집 성공이나 유사성이 인과·영향 관계의 증명은 아닙니다.",
            ),
        ],
    }[level]
    quiz_id = uuid4().hex
    raw_items = []
    items = []
    for position, (question, choices, explanation) in enumerate(question_rows):
        if len(set(choices)) != 4:
            raise EvidenceQuizError("선택지가 중복되어 퀴즈를 구성할 수 없습니다.")
        shift = position % 4
        choices = choices[shift:] + choices[:shift]
        correct = (-shift) % 4
        item_id = f"{quiz_id}-{position + 1}"
        raw_items.append((item_id, question, choices, correct, explanation))
        items.append(
            QuizItem(
                id=item_id,
                question=question,
                choices=[QuizChoice(id=i, text=t) for i, t in enumerate(choices)],
                correct_index=correct,
                explanation=explanation,
            )
        )
    save_quiz_items(
        quiz_id,
        left_id,
        level.value,
        raw_items,
        comparison_id=comparison_id,
        evidence=[field.model_dump(mode="json") for field in fields],
    )
    return QuizResponse(
        quiz_id=quiz_id,
        level=level,
        learning_goal="저장된 공식 근거 읽기·비교·한계 판단",
        items=items,
        comparison_id=comparison_id,
        basis="extracted",
        verification_status=VerificationStatus.NEEDS_REVIEW,
    )
