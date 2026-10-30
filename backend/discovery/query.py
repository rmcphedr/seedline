"""Turn a plain-language discovery request into a result count."""

import re

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "fifteen": 15, "twenty": 20,
}
_PATTERN = re.compile(
    r"\b(?:find|get|search|show|list|discover|need|want)\s+"
    r"(?P<word>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty)\b"
    r"|\b(?P<more>\d{1,2})\s+more\b",
    re.IGNORECASE,
)


def limit_from_query(query: str) -> int | None:
    match = _PATTERN.search(query)
    if match is None:
        return None
    raw = (match.group("word") or match.group("more")).lower()
    number = int(raw) if raw.isdigit() else _WORDS[raw]
    if number > 30:
        return 30
    if number < 1:
        return None
    return number


def resolve_limit(query: str, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    return limit_from_query(query) or 5
