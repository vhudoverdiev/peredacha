from __future__ import annotations

from markupsafe import Markup, escape

from app.services.uid_service import split_cell_remarks

OPEN_TO_CLOSE_QUOTES = {
    '"': '"',
    '«': '»',
    '“': '”',
    '„': '“',
    '‹': '›',
}

OPEN_QUOTES = set(OPEN_TO_CLOSE_QUOTES)
CLOSE_QUOTES = set(OPEN_TO_CLOSE_QUOTES.values())


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


def _sentence_ranges(text: str) -> list[tuple[int, int]]:
    """Split display ranges by the same rules as Excel import."""
    if not text:
        return []

    fragments = split_cell_remarks(text)
    if len(fragments) <= 1:
        return [(0, len(text))]

    ranges: list[tuple[int, int]] = []
    cursor = 0
    for fragment in fragments:
        needle = fragment.strip()
        if not needle:
            continue
        needle_start = text.find(needle, cursor)
        if needle_start < 0:
            return [(0, len(text))]
        start = cursor if text[cursor:needle_start].strip() == "" else needle_start
        end = needle_start + len(needle)
        ranges.append((start, end))
        cursor = end
    return ranges or [(0, len(text))]


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


def remark_plain_text_html(value: object) -> Markup:
    """Render remark text without visual sentence splitting."""
    return remark_text_html(value)
