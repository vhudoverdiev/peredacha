import hashlib
import re
from datetime import date, datetime
from typing import Iterable


SPACE_RE = re.compile(r"\s+")
POINT_RE = re.compile(r"(?:пункт|п\.?|№)?\s*(\d{1,3})", re.IGNORECASE)
DATE_ONLY_RE = re.compile(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$")
DATETIME_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ t]\d{2}:\d{2}(?::\d{2})?)?$", re.IGNORECASE)


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


def extract_point_number(header: str, fallback_index: int | None = None) -> str:
    text = normalize_text(header)
    match = POINT_RE.search(text)
    if match:
        return match.group(1)
    if fallback_index is not None:
        return str(fallback_index)
    return text[:30] or "unknown"


def split_cell_remarks(value) -> list[str]:
    """Return the source cell as one CRM remark.

    В этой CRM одна заполненная ячейка Excel = одно замечание.
    Поэтому не делим текст по переносам строк и точкам с запятой: иначе
    в списке отображается только кусок ячейки, а не полное замечание.
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
    return [text]


def cell_hash(value) -> str:
    # For conflict detection we need a hash sensitive to any change (even one character).
    raw = str(value or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
