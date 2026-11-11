"""Recognize explicit heritage requests without treating a search title as an answer."""

import re


def heritage_subject(text):
    """A narrow name recognizer, not a classifier for arbitrary historical questions."""
    clean = text.strip(" .!?？")
    if re.search(r"말고|대신|아니라", clean):
        return ""
    clean = re.sub(r"^(?:저는|나는|그럼|그러면)\s+", "", clean)
    name = re.split(
        r"(?:에\s*(?:대해|대하여|관해|관하여)|(?:은|는|을|를|이|가)\s+|\s+)", clean, maxsplit=1
    )[0]
    if name in {"역사", "한국사", "세계사", "국사", "고대사", "근대사", "조선사", "고려사"}:
        return ""
    if re.fullmatch(
        r"[가-힣]{2,30}(?:궁|궁궐|탑|석굴|사찰|성곽|산성|왕릉|고분|성당|사|전|문)", name
    ):
        return name
    return ""


def overview_requested(text):
    return bool(heritage_subject(text)) and not re.search(
        r"비교|퀴즈|오답|문제|뜻|재료|언제|시대|구조|모양|종교|무엇으로|뭘로", text
    )


def matching_target(subject, rows):
    """Select a unique name match; never turn a palace into one of its buildings."""
    if not subject:
        return None
    matches = [
        row
        for row in rows
        if not row.get("metadata_only")
        and (row.get("name") == subject or row.get("name", "").endswith(" " + subject))
    ]
    return matches[0] if len(matches) == 1 else None


def overview_excerpt(content, subject=""):
    """Use a complete original paragraph or sentences, bounded to the citation contract."""
    paragraphs = [p.strip() for p in content.splitlines() if p.strip()]
    paragraphs = [p for p in paragraphs if len(p) >= 20]
    target = subject.split()[-1] if subject else ""
    text = (
        next((p for p in paragraphs if target in p), "")
        if len(target) >= 2
        else paragraphs[0]
        if paragraphs
        else ""
    )
    if len(text) <= 700:
        return text
    sentences = re.split(r"(?<=[.!?。])\s+", text)
    selected = []
    for sentence in sentences:
        if len(" ".join(selected + [sentence])) > 700:
            break
        selected.append(sentence)
    # Do not truncate a long sentence, which could remove a qualification or negation.
    return " ".join(selected)
