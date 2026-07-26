from __future__ import annotations

import re

from markupsafe import Markup, escape

OPEN_TO_CLOSE_QUOTES = {
    '"': '"',
    '«': '»',
    '“': '”',
    '„': '“',
    '‹': '›',
}

OPEN_QUOTES = set(OPEN_TO_CLOSE_QUOTES)
CLOSE_QUOTES = set(OPEN_TO_CLOSE_QUOTES.values())

_SENTENCE_CLOSERS = frozenset('"\'»”’)]}')
_SENTENCE_OPENERS = frozenset('"\'«“„‹([{')
_NON_TERMINAL_ABBREVIATIONS = (
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
_INITIALS_SUFFIX_RE = re.compile(r"(?:^|[^А-ЯЁA-Z])(?:[А-ЯЁA-Z]\.){1,3}$")


def _quoted_ranges(text: str) -> list[tuple[int, int]]:
    """Return ranges wrapped in quotation marks, including the quote characters."""
    ranges: list[tuple[int, int]] = []
    stack: list[tuple[str, str, int]] = []
    for idx, char in enumerate(text):
        if char in OPEN_TO_CLOSE_QUOTES:
            # Straight quotes act as both opener and closer.
            if char == '"' and stack and stack[-1][1] == char:
                _, _, start = stack.pop()
                if idx > start:
                    ranges.append((start, idx + 1))
            else:
                stack.append((char, OPEN_TO_CLOSE_QUOTES[char], idx))
            continue
        if stack and char == stack[-1][1]:
            _, _, start = stack.pop()
            if idx > start:
                ranges.append((start, idx + 1))
    ranges.sort()
    return ranges


def has_quoted_remark_text(value: object) -> bool:
    text = str(value or '').strip()
    return bool(text and _quoted_ranges(text))


def _escaped_text_range_html(
    text: str,
    start: int,
    end: int,
    quoted_ranges: list[tuple[int, int]],
) -> str:
    chunks: list[str] = []
    pos = start
    for quote_start, quote_end in quoted_ranges:
        if quote_end <= start:
            continue
        if quote_start >= end:
            break
        overlap_start = max(start, quote_start)
        overlap_end = min(end, quote_end)
        if overlap_start > pos:
            chunks.append(str(escape(text[pos:overlap_start])))
        if overlap_end > overlap_start:
            chunks.append(
                f'<span class="remark-quoted-strike">'
                f'{escape(text[overlap_start:overlap_end])}'
                f'</span>'
            )
        pos = max(pos, overlap_end)
    if pos < end:
        chunks.append(str(escape(text[pos:end])))
    return Markup(''.join(chunks))


def _has_non_terminal_abbreviation(text: str, dot_index: int) -> bool:
    prefix = text[:dot_index + 1].lower()
    for abbreviation in _NON_TERMINAL_ABBREVIATIONS:
        if not prefix.endswith(abbreviation):
            continue
        start = len(prefix) - len(abbreviation)
        if start == 0 or not prefix[start - 1].isalnum():
            return True
    return bool(_INITIALS_SUFFIX_RE.search(text[:dot_index + 1]))


def _sentence_ranges(text: str) -> list[tuple[int, int]]:
    """Split display ranges without changing or dropping source characters."""
    if not text:
        return []

    ranges: list[tuple[int, int]] = []
    line_start = 0
    index = 0
    text_length = len(text)

    while index < text_length:
        char = text[index]
        if char not in ".;":
            index += 1
            continue

        punctuation_end = index + 1
        while punctuation_end < text_length and text[punctuation_end] in _SENTENCE_CLOSERS:
            punctuation_end += 1
        boundary = punctuation_end
        while boundary < text_length and text[boundary].isspace():
            boundary += 1
        sentence_letter_index = boundary
        while sentence_letter_index < text_length and text[sentence_letter_index] in _SENTENCE_OPENERS:
            sentence_letter_index += 1
            while sentence_letter_index < text_length and text[sentence_letter_index].isspace():
                sentence_letter_index += 1

        has_following_sentence = (
            sentence_letter_index < text_length
            and text[sentence_letter_index].isalpha()
            and text[sentence_letter_index].isupper()
        )
        numeric_list_prefix = bool(
            re.search(r"(?:^|\s)\d+\.$", text[:index + 1])
        )
        non_terminal_dot = (
            char == "."
            and (
                _has_non_terminal_abbreviation(text, index)
                or numeric_list_prefix
            )
        )
        should_split = (
            char == ";"
            and boundary < text_length
        ) or (
            char == "."
            and has_following_sentence
            and not non_terminal_dot
        )
        if should_split:
            ranges.append((line_start, boundary))
            line_start = boundary
        index = max(punctuation_end, boundary if boundary == line_start else punctuation_end)

    if line_start < text_length:
        ranges.append((line_start, text_length))
    return ranges or [(0, text_length)]


def remark_text_html(value: object) -> Markup:
    """Escape remark text and strike through fragments wrapped in quotes."""
    text = str(value or '')
    if not text:
        return Markup('')
    ranges = _quoted_ranges(text)
    return Markup(_escaped_text_range_html(text, 0, len(text), ranges))


def remark_sentence_lines_html(value: object) -> Markup:
    """Render every sentence on its own visual line without mutating the text."""
    text = str(value or '')
    if not text:
        return Markup('')

    sentence_ranges = _sentence_ranges(text)
    if len(sentence_ranges) <= 1:
        return remark_text_html(text)

    quoted_ranges = _quoted_ranges(text)
    chunks = [
        (
            '<span class="remark-sentence-line">'
            f'{_escaped_text_range_html(text, start, end, quoted_ranges)}'
            '</span>'
        )
        for start, end in sentence_ranges
    ]
    return Markup(''.join(chunks))
