import hashlib
import re
from datetime import date, datetime
from typing import Iterable


SPACE_RE = re.compile(r"\s+")
POINT_RE = re.compile(r"(?:пункт|п\.?|№)?\s*(\d{1,3})", re.IGNORECASE)
DATE_ONLY_RE = re.compile(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$")
DATETIME_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ t]\d{2}:\d{2}(?::\d{2})?)?$", re.IGNORECASE)
SENTENCE_OPENERS = frozenset('"\'«“„‹([{')
NON_TERMINAL_ABBREVIATIONS = (
    "в т.ч.",
    "и т.д.",
    "и т.п.",
    "т.е.",
    "т.к.",
    "т.п.",
    "т.д.",
    "т.ч.",
    "г.",
    "ул.",
    "им.",
    "пос.",
    "корп.",
    "стр.",
    "рис.",
    "кв.",
    "ком.",
    "п.",
    "ч.",
)
INITIALS_SUFFIX_RE = re.compile(r"(?:^|[^А-ЯЁA-Z])(?:[А-ЯЁA-Z]\.){1,3}$")


def normalize_text(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip().lower()
    text = SPACE_RE.sub(" ", text)
    return text


def stable_hash(parts: Iterable[str]) -> str:
    raw = "|".join(normalize_text(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_task_uid(
    project_name: str,
    construction_number: str,
    apartment_number: str,
    work_point_number: str,
    work_point_name: str,
    remark_text: str,
) -> str:
    remark = normalize_text(remark_text)
    if remark:
        return stable_hash([project_name, construction_number, apartment_number, work_point_number, remark])
    return stable_hash([project_name, construction_number, apartment_number, work_point_number, work_point_name])


def build_source_fragment_uid(
    project_name: str,
    sheet_name: str,
    row_index: int,
    column_index: int,
    fragment_index: int,
) -> str:
    """Return a stable identity for one remark inside an imported source cell."""
    return stable_hash(
        [
            "source-fragment-v1",
            project_name,
            sheet_name,
            str(row_index),
            str(column_index),
            str(fragment_index),
        ]
    )


def extract_point_number(header: str, fallback_index: int | None = None) -> str:
    text = normalize_text(header)
    match = POINT_RE.search(text)
    if match:
        return match.group(1)
    if fallback_index is not None:
        return str(fallback_index)
    return text[:30] or "unknown"


def _has_non_terminal_abbreviation(text: str, dot_index: int) -> bool:
    prefix = text[:dot_index + 1].lower()
    for abbreviation in NON_TERMINAL_ABBREVIATIONS:
        if not prefix.endswith(abbreviation):
            continue
        start = len(prefix) - len(abbreviation)
        if start == 0 or not prefix[start - 1].isalnum():
            return True
    return bool(INITIALS_SUFFIX_RE.search(text[:dot_index + 1]))


def _next_sentence_letter(text: str, start: int) -> tuple[int, str]:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    while index < len(text) and text[index] in SENTENCE_OPENERS:
        index += 1
        while index < len(text) and text[index].isspace():
            index += 1
    return index, text[index] if index < len(text) else ""


def split_cell_remarks(value) -> list[str]:
    """Split a source value into independent CRM remarks.

    A full stop is a boundary only when the next sentence starts with an
    uppercase letter. A semicolon is always a boundary. Dates, decimals,
    abbreviations, initials and numbered prefixes stay intact.
    """
    if value is None:
        return []
    if isinstance(value, (datetime, date)):
        return []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return []

    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if DATE_ONLY_RE.match(text) or DATETIME_ONLY_RE.match(text):
        return []
    if not re.search(r"[A-Za-zА-Яа-яЁё]", text):
        return []

    fragments: list[str] = []
    fragment_start = 0
    index = 0
    while index < len(text):
        char = text[index]
        boundary = False
        boundary_end = index + 1

        if char == ";":
            boundary = True
        elif char == ".":
            next_index, next_char = _next_sentence_letter(text, index + 1)
            numbered_prefix = bool(
                re.search(r"(?:^|\s)\d+\.$", text[:index + 1])
            )
            boundary = bool(
                next_char
                and next_char.isalpha()
                and next_char.isupper()
                and not numbered_prefix
                and not _has_non_terminal_abbreviation(text, index)
            )
            if boundary:
                boundary_end = next_index

        if boundary:
            fragment = text[fragment_start:index + 1].strip()
            if fragment:
                fragments.append(fragment)
            fragment_start = boundary_end
            index = boundary_end
            continue
        index += 1

    tail = text[fragment_start:].strip()
    if tail:
        fragments.append(tail)
    return fragments


def cell_hash(value) -> str:
    # For conflict detection we need a hash sensitive to any change (even one character).
    raw = str(value or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
