from __future__ import annotations

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


def remark_text_html(value: object) -> Markup:
    """Escape remark text and strike through fragments wrapped in quotes."""
    text = str(value or '')
    if not text:
        return Markup('')
    ranges = _quoted_ranges(text)
    if not ranges:
        return Markup(escape(text))

    chunks: list[str] = []
    pos = 0
    for start, end in ranges:
        if start < pos:
            continue
        if start > pos:
            chunks.append(str(escape(text[pos:start])))
        chunks.append(f'<span class="remark-quoted-strike">{escape(text[start:end])}</span>')
        pos = end
    if pos < len(text):
        chunks.append(str(escape(text[pos:])))
    return Markup(''.join(chunks))
