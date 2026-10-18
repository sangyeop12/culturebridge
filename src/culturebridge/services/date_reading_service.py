"""Read one explicitly stated period without inventing precision or mixing events."""

import re
from dataclasses import dataclass

UNCERTAINTY = (
    r"추측|추정|전해|전하|알려|다고 한다|경에|무렵|약\s*\d"
    r"|\b(?:probably|estimated|possibly|believed|around|about)\b|according to tradition"
)


def uncertain_date(quote):
    return bool(re.search(UNCERTAINTY, quote, re.I))


@dataclass(frozen=True)
class PeriodReading:
    text: str
    choices: tuple[str, ...]


def read_period(quote):
    if re.search(r"\bnot\b|without|아니|않|없", quote, re.I):
        return None
    # A sentence with several construction stages is not a single date question.
    if re.search(r"several stages|여러 단계", quote, re.I):
        return None
    era = "기원전 " if re.search(r"\b(?:BC|BCE)\b|기원전", quote, re.I) else ""
    approx = "약 " if re.search(r"\b(?:around|about)\b|약\s*\d|무렵|경에", quote, re.I) else ""
    interval = re.search(
        r"(?:between|from)\s+(\d{3,4})\s*(?:and|to|[-–—])\s*(\d{3,4})"
        r"|\b(\d{3,4})\s*[-–—~]\s*(\d{3,4})\b"
        r"|(\d{3,4})년부터\s*(\d{3,4})년",
        quote,
        re.I,
    )
    if interval:
        values = [int(n) for n in interval.groups() if n]
        # Ignore ambiguous sentences that contain another date outside this range.
        rest = quote[: interval.start()] + quote[interval.end() :]
        if re.search(r"\b\d{3,4}\b|\d{3,4}년", rest):
            return None
        a, b = values
        choices = tuple(f"{era}{approx}{a + shift}~{b + shift}년" for shift in (0, 100, 200, 300))
        return PeriodReading(choices[0], choices)
    century = re.search(
        r"(?:(early|middle|mid|late)[ -]*(?:of the\s+)?)?"
        r"(\d{1,2})(?:st|nd|rd|th)[ -]century"
        r"|(\d{1,2})세기\s*(초반|중엽|중반|후반)?",
        quote,
        re.I,
    )
    if century:
        rest = quote[: century.start()] + quote[century.end() :]
        if re.search(r"\d{3,4}|\d{1,2}세기|\d{1,2}(?:st|nd|rd|th)[ -]century", rest, re.I):
            return None
        number = int(century.group(2) or century.group(3))
        qualifier = century.group(4) or {
            "early": "초반",
            "middle": "중엽",
            "mid": "중엽",
            "late": "후반",
        }.get((century.group(1) or "").lower(), "")
        numbers = [number] + [n for n in (number - 1, number + 1, number + 2, number + 3) if n > 0]
        choices = tuple((f"{era}{approx}{n}세기 {qualifier}").strip() for n in numbers[:4])
        return PeriodReading(choices[0], choices)
    years = list(re.finditer(r"\b(\d{3,4})\b|(\d{3,4})년", quote))
    if len(years) != 1:
        return None
    year = int(next(n for n in years[0].groups() if n))
    if re.search(r"년\s*전|years? ago", quote, re.I):
        return None  # A relative age is not a calendar year.
    choices = tuple(f"{era}{approx}{year + shift}년" for shift in (0, 100, 200, 300))
    return PeriodReading(choices[0], choices)
