"""Conservative subject/scope screening, not a historical truth classifier."""

import re


def sentences(text):
    return [
        s.strip() for s in re.split(r"(?<=[.!?。])(?:\s+|(?=[가-힣『]))|\n+", text) if s.strip()
    ]


def primary_type(name, text=""):
    patterns = [
        ("Pagoda", r"석탑|목탑|다보탑|삼층|오층|탑\b|pagoda|stupa"),
        ("Grotto", r"석굴|grotto|cave"),
        ("Tomb", r"고분|무덤|tomb|mausoleum"),
        ("Palace", r"궁전|궁궐|palace"),
        ("Fort", r"성곽|castle|fort"),
        ("Temple", r"사찰|사원|temple|monastery"),
        ("Church", r"교회|church|cathedral"),
        ("Mosque", r"모스크|mosque"),
    ]
    for candidate in (name, " ".join(sentences(text)[:1])):
        for label, pattern in patterns:
            if re.search(pattern, candidate, re.IGNORECASE):
                return label
    return None


def is_group(name, text=""):
    return bool(
        re.search(
            r"network|corridor|routes|complex\b|monuments\b|historic centre"
            r"|historic areas|landscapes"
            r"|archaeological landscape"
            r"|two temples|동서|동·서|일괄|유적군",
            name,
            re.IGNORECASE,
        )
        or re.search(r"\b(?:thirty-three|\d{2,}) components\b", text, re.IGNORECASE)
    )


def focused_text(source):
    if not source.heritage_id.startswith("khs:") or primary_type(source.title) != "Pagoda":
        return source.content
    short_name = source.title.split()[-1]
    active = False
    selected = []
    for sentence in sentences(source.content):
        # Ancestor/site history is not the construction date of the selected tower.
        if re.match(
            r"(?:불국사|석굴암|석가탑)(?:는|은|를|을|가|이|의|을 보면)", sentence
        ) and not sentence.startswith(short_name):
            active = False
            continue
        if short_name in sentence:
            active = True
        if re.match(r"(?:탑이|탑은|이 탑|이탑)", sentence):
            active = True
        if active:
            selected.append(sentence)
    return "\n".join(selected)


def quote_matches_subject(source, quote):
    return quote in focused_text(source)
