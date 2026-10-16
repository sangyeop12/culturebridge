"""Conservative subject/scope screening, not a historical truth classifier."""

import re


def sentences(text):
    return [
        s.strip() for s in re.split(r"(?<=[.!?。])(?:\s+|(?=[가-힣『]))|\n+", text) if s.strip()
    ]


def primary_type(name, text=""):
    patterns = [
        ("Pagoda", r"석탑|목탑|다보탑|탑\b|pagoda|stupa"),
        ("Grotto", r"석굴|grotto|cave"),
        ("Tomb", r"고분|무덤|왕릉|\b묘\b|묘당|[가-힣]+(?:총|릉)\b|tomb|mausoleum"),
        ("Palace", r"궁전|궁궐|\b어전\b|[가-힣]+궁\b|palace"),
        ("Fort", r"성곽|castle|fort"),
        ("Hall", r"[가-힣]+(?:전|각|루)\b|본당|봉황당|대연회장|\bhall\b|pavilion"),
        ("Gate", r"[가-힣]+문\b|\bgate\b"),
        ("Temple", r"사찰|사원|[가-힣]+사\b|temple|monastery"),
        ("Church", r"교회|성당|예배당|수도원|church|cathedral|chapel|abbey"),
        ("Mosque", r"모스크|mosque"),
        ("Megalith", r"고인돌|거석|스톤헨지|stonehenge|dolmen|megalith|stone circle"),
    ]
    # A compound Korean title identifies its last component, not its parent site.
    title = name.split()[-1] if re.search(r"[가-힣]", name) else name
    if re.fullmatch(r"[가-힣]+성", title):
        return "Fort"  # A title ending in 성, not prose such as "완성" or "가능성".
    # A named component at the end of an English title takes precedence over its site:
    # "Edinburgh Castle Great Hall" describes a hall, not the whole castle.
    if not re.search(r"[가-힣]", name):
        component = re.search(
            r"\b(pagoda|stupa|hall|pavilion|chapel|cathedral|mausoleum|palace)\s*$",
            name,
            re.I,
        )
        if component:
            title = component.group(1)
    for candidate in (title, " ".join(sentences(text)[:1])):
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
        or re.search(
            r"\b(?:two|three|four|five|six|seven|eight|nine|ten|thirty-three|[2-9]|\d{2,})"
            r"\s+(?:separate\s+)?components\b|[2-9]\d*개(?:의)?\s*(?:구성|유산|사찰|건물)",
            text,
            re.IGNORECASE,
        )
    )


def subtype(name, text=""):
    """Only explicit material/type; an unknown subtype is not a mismatch."""
    for value in (name, text):
        if re.search(r"석탑|stone\s+(?:pagoda|stupa)", value, re.I):
            return "stone_pagoda"
        if re.search(r"목탑|wood(?:en)?\s+(?:pagoda|stupa)", value, re.I):
            return "wooden_pagoda"
    return None


def date_event(quote):
    if re.search(r"재건|중건|중창|복원|다시 세|rebuild|rebuilt|reconstruct|restor", quote, re.I):
        return "재건·복원"
    if re.search(r"창건|건립|조성|축조|설립|세운|세웠|built|construct|erect|found", quote, re.I):
        return "건립·창건"
    return "시대·사건 확인 필요"


def focused_text(source):
    if source.content_kind not in {"individual_text", "listed_text"}:
        return source.content
    if is_group(source.title, source.content):
        return source.content
    short_name = source.title.split()[-1]
    kind = primary_type(source.title, source.content)
    generic = {
        "Pagoda": r"탑|석탑|목탑|pagoda|stupa",
        "Temple": r"사찰|사원|절|temple|monastery",
        "Palace": r"궁|궁궐|궁전|palace",
        "Tomb": r"고분|무덤|왕릉|능|묘|봉분|tomb|mausoleum|mound",
        "Fort": r"성|성곽|fort|castle",
        "Grotto": r"석굴|동굴|cave|grotto",
        "Church": r"교회|성당|예배당|수도원|church|cathedral|chapel|abbey",
        "Megalith": r"고인돌|거석|스톤헨지|stonehenge|dolmen|megalith|stone circle|monument",
        "Mosque": r"모스크|mosque",
        "Hall": r"전각|건물|hall|pavilion",
        "Gate": r"문|gate",
    }.get(kind, r"탑|사찰|사원|궁궐|궁전|고분|무덤|성곽|석굴|pagoda|stupa|temple|palace|tomb|cave")
    # A standalone provider introduction may omit the name ("Built in ...").
    active = True
    selected = []
    subject_names = ()
    if source.id == source.heritage_id and source.id.startswith("official:"):
        from culturebridge.services.individual_source_service import INDIVIDUALS

        subject_names = INDIVIDUALS.get(source.id.split(":", 1)[1], {}).get("subject_names", ())
    for sentence in sentences(source.content):
        if (
            re.search(r"[A-Za-z]", sentence)
            and not re.search(r"[.!?]", sentence)
            and not re.search(
                r"\b(?:is|was|were|has|contains|stands|dates|built|constructed|founded|made|located)\b",
                sentence,
                re.I,
            )
        ):
            continue  # A page title is not a descriptive sentence.
        # Lists of possessions/nearby monuments do not describe the site's own material.
        if re.match(r"^(?:그 밖에|그밖에|현재 절 안에는|경내 비각에는)", sentence):
            active = False
            continue
        component_object = re.search(
            r"([가-힣]+(?:전|각|문|루|탑))(?:을|를)\s*(?:만들|세|건립|재건)", sentence
        )
        if component_object and component_object.group(1) != short_name:
            active = False
            continue
        owned = re.match(
            r"^[가-힣\s]+의\s+([가-힣]+(?:탑|전|각|문|사|궁|릉|총|묘|석굴))(?:은|는|이|가)",
            sentence,
        )
        if owned and owned.group(1) != short_name:
            active = False
            continue
        korean_subject = re.match(
            r"^([가-힣·]+(?:\s+[가-힣·]+){0,2}?"
            r"(?:탑|사|궁|궁궐|사찰|전|각|문|릉|총|묘|고분|무덤|석굴))(?:은|는|이|가|의)\s*",
            sentence,
        )
        english_subject = re.match(
            r"^(?:The\s+)?([A-Za-z -]*?\b"
            r"(?:temple|palace|pagoda|stupa|tomb|hall|gate|cave|fort))\s+"
            r"(?:was|is|were|has|dates|contains|stands)",
            sentence,
            re.I,
        )
        subject = korean_subject or english_subject
        if subject:
            named = subject.group(1).strip()
            named = re.sub(r"^The\s+", "", named, flags=re.I)
            is_target = (
                source.title.casefold() in named.casefold()
                or (bool(re.search(r"[가-힣]", short_name)) and short_name in named)
                or any(alias.casefold() == named.casefold() for alias in subject_names)
            )
            is_generic = bool(
                re.fullmatch(r"(?:이\s*|이곳의\s*)?(?:" + generic + r")", named, re.I)
            )
            if english_subject:
                is_generic = is_generic or bool(
                    re.fullmatch(
                        r"(?:(?:a|an)\s+)?(?:(?:ancient|artificial|stone|wooden|royal|"
                        r"Buddhist|marble|granite|brick)\s+)*(?:" + generic + r")",
                        named,
                        re.I,
                    )
                )
            if not is_target and not is_generic:
                active = False
                continue
            active = True
        elif short_name in sentence or source.title in sentence:
            active = True
        elif re.match(
            r"^(?:이\s*|이곳의\s*)?(?:" + generic + r")(?:은|는|이|가|의)\s*", sentence, re.I
        ):
            active = True
        # A person's biography is not the age of the monument.
        if re.search(r"태어|생몰|출생|born|lived from", sentence, re.I):
            active = False
            continue
        if active:
            selected.append(sentence)
    return "\n".join(selected)


def quote_matches_subject(source, quote):
    return quote in focused_text(source)
