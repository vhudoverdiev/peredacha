from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Any, Iterable

from sqlalchemy import Integer, cast, case, func, or_, and_
from app import db
from app.models import (
    AppSetting,
    Apartment,
    Project,
    SyncConflict,
    Task,
    User,
    WorkCategory,
    WorkPoint,
    STATUS_DONE,
    STATUS_FINISHERS,
    STATUS_CONTRACTOR,
    DONE_STATUSES,
    STATUS_NOT_STARTED,
)
from app.services.changelog_service import log_change
from app.services.mapping_service import ensure_default_categories, apply_default_point_mapping
from app.services.uid_service import build_task_uid, cell_hash, extract_point_number, normalize_text, split_cell_remarks


APARTMENT_HEADERS = {
    "apartment_number": ["квартира", "кв", "помещение", "номер квартиры"],
    "construction_number": ["строительный", "строит", "стр. №", "строительный номер"],
    "owner_name": ["собственник", "владелец", "фио"],
    "phone": ["телефон", "тел", "контакт"],
    "finishing_type": ["отделка", "вид отделки"],
    "entrance": ["подъезд", "секция"],
    "floor": ["этаж"],
    "inspection_date": ["дата осмотра", "осмотр"],
    "reinspection_date": ["повтор", "переосмотр"],
    "app_signed_date": ["дата подписания апп", "апп"],
    "deadline_date": ["срок передачи", "дата передачи"],
    "remark_deadline_date": ["срок устранения замечаний по апп"],
    "comment": ["комментарий", "примечание"],
}

IGNORED_POINT_HEADER_PARTS = [
    "квартира",
    "помещение",
    "строительный",
    "собственник",
    "телефон",
    "отделка",
    "подъезд",
    "секция",
    "этаж",
    "дата",
    "комментарий",
    "примечание",
    "авр",
]

# Cyrillic aliases for matching real Excel headers.
APARTMENT_HEADERS_RU = {
    "apartment_number": ["квартира", "кв", "помещение", "номер квартиры"],
    "construction_number": ["строительный", "строит", "стр. №", "строительный номер", "стр №", "стр.№"],
    "owner_name": ["собственник", "владелец", "фио"],
    "phone": ["телефон", "тел", "контакт"],
    "finishing_type": ["отделка", "вид отделки"],
    "entrance": ["подъезд", "секция"],
    "floor": ["этаж"],
    "inspection_date": ["дата осмотра", "осмотр"],
    "reinspection_date": ["повтор", "переосмотр"],
    "app_signed_date": ["дата подписания апп", "апп"],
    "deadline_date": ["срок передачи", "дата передачи"],
    "remark_deadline_date": ["срок устранения замечаний по апп"],
    "comment": ["комментарий", "примечание"],
}

IGNORED_POINT_HEADER_PARTS_RU = [
    "квартира",
    "помещение",
    "строительный",
    "собственник",
    "телефон",
    "отделка",
    "подъезд",
    "секция",
    "этаж",
    "дата",
    "комментарий",
    "примечание",
    "авр",
]

APARTMENT_IMPORT_CONFLICT_LABELS = {
    "owner_name": "Собственник",
    "is_unsold": "Не продано",
    "phone": "Телефон",
    "finishing_type": "Вид отделки",
    "entrance": "Подъезд / секция",
    "floor": "Этаж",
    "inspection_date": "Дата осмотра",
    "reinspection_date": "Повторный осмотр",
    "deadline_date": "Дата АПП / срок передачи",
    "remark_deadline_date": "Срок устранения замечаний по АПП",
    "app_deadline_date": "Срок устранения замечаний по АПП",
    "app_deadline_raw": "Срок устранения замечаний по АПП",
    "app_deadline_status": "Статус срока АПП",
    "is_app_mode": "Режим АПП",
    "avr_status": "АВР",
    "avr_signed_date": "Дата подписания АВР",
    "comment": "Комментарий",
    "inspection_note": "Комментарий осмотра",
}

# Основные рабочие замечания для вкладки "Все" и рабочих разделов: пункты 10-22.
MAIN_WORK_POINT_NUMBERS = {str(number) for number in range(10, 23)}
# Доп. соглашение хранится отдельно: в исходной таблице материалы лежат в пункте 24.
DOP_AGREEMENT_POINT_NUMBERS = {"24"}
# Импортировать можно основные замечания + доп. соглашение, но во вкладку "Все" попадают только 10-22.
VISIBLE_WORK_POINT_NUMBERS = MAIN_WORK_POINT_NUMBERS | DOP_AGREEMENT_POINT_NUMBERS

AVR_STATUS_NEEDED = "needed"
AVR_STATUS_SIGNED = "signed"
APP_DEADLINE_NORMAL = "normal"
APP_DEADLINE_EXPIRING = "expiring"
APP_DEADLINE_EXPIRED = "expired"
APP_DEADLINE_NO_REMARKS = "no_remarks"
UNSOLD_OWNER_MARKERS = ("не продано", "непродано", "не продан", "не продана", "нет собственника")
SERVICE_PREMISE_WORDS = ("корпус", "подъезд", "очеред", "секц", "итог", "дом")

CONSTRUCTION_QUERY_RE = re.compile(r"\b\d+-\d+-\d+\b")
PREMISE_PAIR_QUERY_RE = re.compile(
    r"\b(?:кв|к|комм|коммерция|помещение|пом)?\s*(\d+)\s*/\s*(?:к|корпус)?\s*(\d+)\b",
    re.IGNORECASE,
)
PREMISE_QUERY_RE = re.compile(r"\b(кв|квартира|к|комм|коммерция|помещение|пом)\D{0,12}(\d+)\b", re.IGNORECASE)
PREMISE_SUFFIX_QUERY_RE = re.compile(r"\b(\d+)\s*(?:к|кв|комм)\b", re.IGNORECASE)
PREMISE_SEARCH_MODES = {
    "construction_number",
    "commercial_pair",
    "premise_number",
    "premise_number_or_building",
}
LEADING_MULTI_PREMISE_RE = re.compile(
    r"""
    ^\s*
    (
        \d+-\d+-\d+
        |
        (?:кв|к|комм|коммерция|помещение|пом)?\s*\d+\s*/\s*(?:к|корпус)?\s*\d+
        |
        (?:кв|квартира|к|комм|коммерция|помещение|пом)\D{0,12}\d+
        |
        \d+\s*(?:к|кв|комм)
        |
        \d+
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def detect_search_mode(query: str | None) -> tuple[str, str]:
    """Возвращает режим поиска: по номеру помещения или обычный текстовый поиск."""
    text = str(query or "").strip()
    if not text:
        return "text", ""
    normalized = normalize_text(text).replace("ё", "е")
    if CONSTRUCTION_QUERY_RE.fullmatch(normalized):
        return "construction_number", normalized
    match = PREMISE_PAIR_QUERY_RE.search(normalized)
    if match:
        return "commercial_pair", f"{match.group(1)}|{match.group(2)}"
    if text.isdigit():
        return "premise_number", text
    match = PREMISE_QUERY_RE.search(normalized)
    if match:
        prefix, number = match.group(1), match.group(2)
        if prefix == "к":
            return "premise_number_or_building", number
        return "premise_number", number
    match = PREMISE_SUFFIX_QUERY_RE.search(normalized)
    if match:
        return "premise_number", match.group(1)
    return "text", text


def parse_multi_premise_search(query: str | None) -> tuple[list[tuple[str, str]], str]:
    text = str(query or "").strip()
    if not text:
        return [], ""
    selectors: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    cursor = 0
    while cursor < len(text):
        separator_match = re.match(r"\s*(?:[;,]\s*)?", text[cursor:])
        if separator_match:
            cursor += separator_match.end()
        if cursor >= len(text):
            break
        match = LEADING_MULTI_PREMISE_RE.match(text[cursor:])
        if not match:
            break
        part = match.group(1).strip()
        mode, value = detect_search_mode(part)
        if mode not in PREMISE_SEARCH_MODES or not str(value or "").strip():
            break
        selector = (mode, str(value).strip())
        if selector not in seen:
            seen.add(selector)
            selectors.append(selector)
        cursor += match.end()
    if not selectors:
        return [], text
    return selectors, text[cursor:].strip(" \t,;")


def get_multi_param_values(params, key: str) -> list[str]:
    values: list[object] = []
    if hasattr(params, "getlist"):
        try:
            values = list(params.getlist(key))
        except TypeError:
            values = []
    if not values:
        raw = params.get(key) if hasattr(params, "get") else None
        if isinstance(raw, (list, tuple, set)):
            values = list(raw)
        elif raw not in {None, ""}:
            values = [raw]
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        result.extend([part.strip() for part in cleaned.split(",") if part.strip()])
    return result


def premise_matches_selector(apartment: Apartment | None, selector: tuple[str, str]) -> bool:
    mode, value = selector
    return premise_matches_search(apartment, mode, value)


def premise_selector_value(selector: tuple[str, str]) -> str:
    mode, value = selector
    if mode == "commercial_pair":
        number, _, building = str(value).partition("|")
        return f"{number}/{building}".strip("/")
    return str(value or "").strip()


def premise_selector_clause(selector: tuple[str, str]):
    mode, value = selector
    if mode == "commercial_pair":
        number, _, building = str(value).partition("|")
        return and_(
            Apartment.premise_type == "commercial",
            Apartment.apartment_number == number,
            Apartment.building == building,
        )
    if mode == "construction_number":
        return Apartment.construction_number == value
    if mode == "premise_number_or_building":
        return or_(
            Apartment.apartment_number == value,
            and_(Apartment.premise_type == "commercial", Apartment.building == value),
        )
    if mode == "premise_number":
        return Apartment.apartment_number == value
    return None


def premise_matches_search(apartment: Apartment | None, mode: str, value: str | None) -> bool:
    if not apartment or not value:
        return False
    value = str(value).strip()
    if mode == "commercial_pair":
        number, _, building = value.partition("|")
        return (
            (apartment.premise_type or "apartment") == "commercial"
            and str(apartment.apartment_number or "").strip() == number
            and str(apartment.building or "").strip() == building
        )
    if mode == "construction_number":
        return str(apartment.construction_number or "").strip() == value
    if mode == "premise_number_or_building":
        if str(apartment.apartment_number or "").strip() == value:
            return True
        return (apartment.premise_type or "apartment") == "commercial" and str(apartment.building or "").strip() == value
    return premise_matches_number(apartment, value)


def premise_matches_number(apartment: Apartment | None, number: str | None) -> bool:
    number = str(number or "").strip()
    if not apartment or not number:
        return False
    values = [
        str(apartment.apartment_number or "").strip(),
    ]
    for value in values:
        if not value:
            continue
        if value == number:
            return True
    return False


@dataclass
class SyncResult:
    created_count: int = 0
    updated_count: int = 0
    missing_count: int = 0
    seen_uids: set[str] | None = None

    def as_dict(self):
        return {
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "missing_count": self.missing_count,
        }


def get_setting(key: str, default: str | None = None) -> str | None:
    setting = AppSetting.query.filter_by(key=key).first()
    return setting.value if setting else default


def set_setting(key: str, value: str | None) -> None:
    setting = AppSetting.query.filter_by(key=key).first()
    if setting is None:
        setting = AppSetting(key=key, value=value)
        db.session.add(setting)
    else:
        setting.value = value


def get_or_create_project(name: str = "100 Квартал 7 очередь") -> Project:
    project = Project.query.filter_by(name=name).first()
    if project is None:
        project = Project(name=name, description="Создано автоматически при первой синхронизации")
        db.session.add(project)
        db.session.flush()
    return project


def normalize_header_row(row: list[Any]) -> list[str]:
    return [str(cell or "").strip() for cell in row]


def merge_header_rows(upper: list[Any], lower: list[Any]) -> list[str]:
    upper_norm = normalize_header_row(upper)
    lower_norm = normalize_header_row(lower)
    size = max(len(upper_norm), len(lower_norm))
    merged: list[str] = []
    for idx in range(size):
        up = upper_norm[idx] if idx < len(upper_norm) else ""
        lo = lower_norm[idx] if idx < len(lower_norm) else ""
        merged.append(lo if lo else up)
    return merged


def is_index_number_row(row: list[Any]) -> bool:
    non_empty = [str(c).strip() for c in row if str(c or "").strip()]
    if len(non_empty) < 6:
        return False
    numeric = 0
    for v in non_empty:
        s = v.replace(".", "").replace(",", "")
        if s.isdigit():
            numeric += 1
    return numeric / max(len(non_empty), 1) >= 0.7


def find_header_row(rows: list[list[Any]]) -> int:
    best_index = 0
    best_score = -1
    for idx, row in enumerate(rows[:30]):
        normalized = [normalize_text(c) for c in row]
        score = 0
        if is_index_number_row(row):
            score -= 5
        for aliases in APARTMENT_HEADERS_RU.values():
            if any(any(alias in cell for alias in aliases) for cell in normalized):
                score += 1
        if any("пункт" in cell or "пункт" in cell or cell.strip().isdigit() for cell in normalized):
            score += 2
        work_point_hits = 0
        for col_idx, cell in enumerate(row):
            if is_work_point_header(str(cell or ""), col_idx):
                work_point_hits += 1
        score += min(work_point_hits, 12)
        if idx + 1 < len(rows) and is_index_number_row(rows[idx + 1]):
            score += 10
        if idx + 1 < len(rows):
            indexed_hits = sum(1 for raw in rows[idx + 1] if _indexed_visible_point_number(raw))
            if indexed_hits:
                score += min(indexed_hits, 15) * 2
                if indexed_hits >= 5:
                    score += 8
        if score > best_score:
            best_score = score
            best_index = idx
    return best_index


def _header_matches_base_field(field: str, header: str) -> bool:
    if not header:
        return False
    if field == "remark_deadline_date":
        return header == "срок устранения замечаний по апп"
    if field == "app_signed_date":
        return header == "апп" or "дата подписания апп" in header
    return any(alias in header for alias in APARTMENT_HEADERS_RU.get(field, ()))


def map_base_columns(headers: list[str], anchor_before_col: int | None = None) -> dict[str, int]:
    mapping: dict[str, int] = {}
    normalized_headers = [normalize_text(h) for h in headers]
    indexes = range(len(normalized_headers))
    if anchor_before_col is not None:
        indexes = range(max(anchor_before_col, 0))
    # Когда слева от основной таблицы добавили вспомогательный блок с похожими
    # заголовками, нужны колонки именно того блока, который стоит перед пунктами.
    # Поэтому при привязке к первому пункту идём справа налево.
    search_indexes = list(indexes)
    if anchor_before_col is not None:
        search_indexes.reverse()

    for field, aliases in APARTMENT_HEADERS_RU.items():
        for idx in search_indexes:
            header = normalized_headers[idx]
            if _header_matches_base_field(field, header):
                mapping[field] = idx
                break
    return mapping


def _indexed_visible_point_number(raw: Any) -> str | None:
    point_number = None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        point_number = str(int(raw)) if float(raw).is_integer() else str(raw)
    else:
        value = str(raw or "").strip()
        if value.replace(",", ".").replace(" ", "").endswith(".0"):
            value = value.replace(",", ".").replace(" ", "")
        value_norm = value.replace(".", "").replace(",", "")
        if value_norm.isdigit():
            point_number = value.split(".", 1)[0]
    if point_number and point_number.isdigit() and is_visible_work_point_number(point_number):
        return point_number
    return None


def is_work_point_header(header: str, index: int) -> bool:
    h = normalize_text(header)
    if not h:
        return False
    if any(part in h for part in (IGNORED_POINT_HEADER_PARTS_RU + IGNORED_POINT_HEADER_PARTS)):
        return False
    point = extract_point_number(h, None)
    if point.isdigit() and int(point) >= 1:
        return True
    # В таблицах пункт может быть назван просто "10" или "10. Стены".
    if h.split(" ", 1)[0].replace(".", "").isdigit():
        return True
    return False


def map_work_point_columns(headers: list[str], base_mapping: dict[str, int]) -> dict[int, str]:
    base_indexes = set(base_mapping.values())
    points: dict[int, str] = {}
    for idx, header in enumerate(headers):
        if idx in base_indexes:
            continue
        if is_work_point_header(header, idx):
            point_number = extract_point_number(header, idx + 1)
            if is_visible_work_point_number(point_number):
                points[idx] = header
    return points


def _point_column_groups(point_columns: dict[int, str]) -> list[dict[int, str]]:
    if not point_columns:
        return []
    groups: list[dict[int, str]] = []
    current: dict[int, str] = {}
    previous_idx: int | None = None
    previous_point_number: int | None = None
    for idx in sorted(point_columns):
        raw_point_number = extract_point_number(point_columns[idx], idx + 1)
        point_number = int(raw_point_number) if str(raw_point_number).isdigit() else None
        should_split = False
        if previous_idx is not None and idx - previous_idx > 2:
            should_split = True
        elif previous_point_number is not None and point_number is not None and point_number <= previous_point_number:
            # When two remark tables stand close to each other, the visible point
            # numbering usually starts over from 10 in the second table. Treat
            # that reset as a boundary even if there is no wide empty gap.
            should_split = True
        if should_split:
            if current:
                groups.append(current)
            current = {}
        current[idx] = point_columns[idx]
        previous_idx = idx
        previous_point_number = point_number
    if current:
        groups.append(current)
    return groups


def _point_group_score(headers: list[str], group: dict[int, str]) -> tuple[int, int, int, int]:
    if not group:
        return (-10_000, 0, 0, 0)
    first_col = min(group)
    anchored_mapping = map_base_columns(headers, anchor_before_col=first_col)
    identity_hits = int(anchored_mapping.get("apartment_number") is not None) + int(anchored_mapping.get("construction_number") is not None)
    base_hits = sum(1 for value in anchored_mapping.values() if value is not None)
    point_numbers = {
        extract_point_number(header, idx + 1)
        for idx, header in group.items()
        if is_visible_work_point_number(extract_point_number(header, idx + 1))
    }
    main_hits = len(point_numbers & MAIN_WORK_POINT_NUMBERS)
    dop_hits = len(point_numbers & DOP_AGREEMENT_POINT_NUMBERS)
    # The real remarks table has the apartment identity columns immediately before
    # a long run of visible work points. A small auxiliary table on the left may
    # have similar labels, so prefer the richest run with a valid identity anchor.
    score = main_hits * 12 + dop_hits * 5 + len(group) * 2 + identity_hits * 30 + base_hits
    if identity_hits == 0:
        score -= 40
    return (score, main_hits, identity_hits, -first_col)


def select_primary_work_point_columns(headers: list[str], point_columns: dict[int, str]) -> dict[int, str]:
    groups = _point_column_groups(point_columns)
    if len(groups) <= 1:
        return point_columns
    return max(groups, key=lambda group: _point_group_score(headers, group))


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


INSPECTION_SCHEDULE_PREFIX = "__inspection_schedule__:"


def _parse_inspection_schedule_value(value) -> date | datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d/%m/%Y",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            if "%H" in fmt:
                return parsed.replace(microsecond=0)
            return parsed.date()
        except ValueError:
            continue
    return parse_date(text)


def _inspection_schedule_marker(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return f"{INSPECTION_SCHEDULE_PREFIX}{value.replace(microsecond=0).isoformat(timespec='seconds')}"
    return None


def _is_inspection_schedule_marker(value: str | None) -> bool:
    return str(value or "").strip().startswith(INSPECTION_SCHEDULE_PREFIX)


def _discard_pending_inspection_schedule_conflicts(apartment: Apartment) -> None:
    """Remove obsolete conflicts that tried to replace a human comment with a schedule marker."""
    conflicts = SyncConflict.query.filter(
        SyncConflict.status == "pending",
        SyncConflict.target_type == "apartment",
        SyncConflict.apartment_id == apartment.id,
        SyncConflict.field_name == "inspection_note",
        SyncConflict.new_value.like(f"{INSPECTION_SCHEDULE_PREFIX}%"),
    ).all()
    for conflict in conflicts:
        db.session.delete(conflict)


def is_visible_work_point_number(point_number: str | int | None) -> bool:
    if point_number is None:
        return False
    return str(point_number).strip() in VISIBLE_WORK_POINT_NUMBERS


def normalize_finishing_type(value: Any) -> str | None:
    """Return only a real finishing type, not dates/numbers from shifted rows."""
    if value is None or value == "":
        return None
    if isinstance(value, (datetime, date)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return None

    text = str(value).strip()
    if not text:
        return None
    if parse_date(text):
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return None
    except ValueError:
        pass
    return text


def fallback_finishing_type(project: Project, apartment_number: str | None, exclude_apartment_id: int | None = None) -> str | None:
    """Use an already known finishing type for duplicate apartment numbers when the row has no type."""
    if not apartment_number:
        return None
    query = Apartment.query.filter(
        Apartment.project_id == project.id,
        Apartment.apartment_number == apartment_number,
        Apartment.finishing_type.isnot(None),
        Apartment.finishing_type != "",
    )
    if exclude_apartment_id:
        query = query.filter(Apartment.id != exclude_apartment_id)
    existing = query.order_by(Apartment.id.asc()).first()
    return existing.finishing_type if existing else None


def value_at(row: list[Any], index: int | None) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]


def normalize_number_cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()
    text = str(value).strip()
    return text or None


def normalize_apartment_number_cell(value: Any) -> str | None:
    """Normalize an apartment number while discarding a parenthesized alias.

    Some source tables contain values such as ``10 (11)`` where the first
    number is the apartment number and the value in parentheses is an old or
    secondary number. Construction numbers are intentionally not processed by
    this helper.
    """
    text = normalize_number_cell(value)
    if not text:
        return None
    match = re.fullmatch(r"\s*(\d+)\s*\([^)]*\)\s*", text)
    return match.group(1) if match else text


def is_service_premise_text(value: str | None) -> bool:
    text = normalize_text(value or "").replace("ё", "е")
    return bool(text) and any(word in text for word in SERVICE_PREMISE_WORDS)


def looks_like_apartment_identifier(value: str | None) -> bool:
    text = normalize_number_cell(value)
    if not text:
        return False
    if len(text) > 24:
        return False
    if sum(1 for part in text.split() if part) > 2:
        return False
    if any(ch in text for ch in ".,:;!?"):
        return False
    if not any(ch.isdigit() for ch in text):
        return False
    if sum(1 for ch in text if ch.isalpha()) > 4:
        return False
    if not all(ch.isalnum() or ch in {" ", "-", "/", "\\", "(", ")"} for ch in text):
        return False
    normalized = normalize_text(text).replace("С‘", "Рµ")
    return not any(word in normalized for word in SERVICE_PREMISE_WORDS)


def normalize_commercial_number(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = normalize_text(text).replace("ё", "е")
    normalized = re.sub(r"^коммерци[яи]\s*", "", normalized).strip()
    return normalized or text


def apartment_number_from_construction(construction_number: str | None) -> str | None:
    if not construction_number:
        return None
    text = str(construction_number).strip()
    # Typical format: "1-2-6" where the last segment is the apartment number.
    last = text.split("-")[-1].strip()
    return last if last.isdigit() else None


def is_auto_done_remark(remark_text: str) -> bool:
    text = (remark_text or "").strip()
    if not text:
        return False
    if text.startswith("-"):
        return True
    lowered = text.lower()
    return ("автлп" in lowered) and ("(лб" in lowered or " лб)" in lowered)


def detect_status_marker(remark_text: str) -> str | None:
    lowered = (remark_text or "").lower()
    if "(чистовики)" in lowered:
        return STATUS_FINISHERS
    if "(подрядчик)" in lowered or "(подрядчики)" in lowered:
        return STATUS_CONTRACTOR
    if "(лб)" in lowered or is_auto_done_remark(remark_text):
        return STATUS_DONE
    return None


def _pending_text_sync_conflict(task_id: int) -> SyncConflict | None:
    return (
        SyncConflict.query.filter(
            SyncConflict.task_id == task_id,
            SyncConflict.status == "pending",
            SyncConflict.target_type == "task",
            or_(
                SyncConflict.field_name.is_(None),
                SyncConflict.field_name.in_(("source_cell_value", "description")),
            ),
        )
        .order_by(SyncConflict.id.desc())
        .first()
    )


def is_non_white_finishing(finishing_type: str | None) -> bool:
    text = normalize_text(finishing_type or "").replace("ё", "е")
    return bool(text) and text != "белая"


def should_auto_finishers(apartment: Apartment, work_point: WorkPoint) -> bool:
    # Auto-marking finishers for clean-finish apartments is disabled by product rules.
    return False



def is_unsold_owner_name(owner_name: str | None) -> bool:
    text = normalize_text(owner_name or "").replace("ё", "е")
    return bool(text) and any(marker in text for marker in UNSOLD_OWNER_MARKERS)


def is_apartment_unsold(apartment: Apartment | Any) -> bool:
    owner_name = str(getattr(apartment, "owner_name", None) or "").strip()
    if is_unsold_owner_name(owner_name):
        return True
    # Если у квартиры указан реальный собственник, она не должна попадать в
    # «не продано» даже при старой/случайной оранжевой отметке из импорта.
    return bool(getattr(apartment, "is_unsold", False)) and not owner_name


def normalize_building_marker(value: Any) -> str | None:
    text = normalize_text(value or "").replace("ё", "е")
    if not text or "корпус" not in text:
        return None
    import re
    match = re.search(r"(\d+)", text)
    return match.group(1) if match else text


def _has_app_marker(value: Any) -> bool:
    text = normalize_text(value or "").replace("ё", "е")
    return "апп" in text


def is_premise_section_marker(row: list[Any]) -> str | None:
    values = [normalize_text(value) for value in row if str(value or "").strip()]
    if not values:
        return None
    first = values[0]
    if first == "коммерция" and len(values) <= 2:
        return "commercial"
    if first in {"квартиры", "квартира"} and len(values) <= 2:
        return "apartment"
    return None


def apply_app_deadline_logic(apartment: Apartment, raw_value: Any) -> None:
    """Единый импорт срока из колонки «Срок устранения замечаний  по АПП».

    Работает и для квартир, и для коммерций: если в колонке дата — это срок,
    если «без замечаний»/пусто — на сайте показываем «Нет срока».
    """
    text = str(raw_value or "").strip()
    lowered = normalize_text(text).replace("ё", "е")
    parsed_date = parse_date(raw_value)

    apartment.app_deadline_raw = text or None

    if "без замечаний" in lowered:
        apartment.is_app_mode = True
        apartment.app_deadline_date = None
        apartment.remark_deadline_date = None
        apartment.app_deadline_status = APP_DEADLINE_NO_REMARKS
        apartment.avr_status = AVR_STATUS_SIGNED
        apartment.avr_signed_date = apartment.avr_signed_date or apartment.deadline_date or date.today()
        return

    if parsed_date:
        apartment.is_app_mode = True
        apartment.app_deadline_date = parsed_date
        apartment.remark_deadline_date = parsed_date
        apartment.app_deadline_status = APP_DEADLINE_NORMAL
        if apartment.avr_status != AVR_STATUS_SIGNED:
            apartment.avr_status = AVR_STATUS_NEEDED
        return

    apartment.app_deadline_date = None
    apartment.remark_deadline_date = None
    apartment.app_deadline_status = APP_DEADLINE_NORMAL

    if not text:
        if apartment.is_app_mode and apartment.avr_status not in {AVR_STATUS_NEEDED, AVR_STATUS_SIGNED}:
            apartment.avr_status = AVR_STATUS_NEEDED
        return

    # Любой другой текст сохраняем как raw-значение, но не считаем датой.
    if apartment.is_app_mode and apartment.avr_status != AVR_STATUS_SIGNED:
        apartment.avr_status = AVR_STATUS_NEEDED


def _format_import_conflict_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value).strip()


def _import_values_equal(old_value: Any, new_value: Any) -> bool:
    return _format_import_conflict_value(old_value) == _format_import_conflict_value(new_value)


def _has_meaningful_import_value(value: Any) -> bool:
    return _format_import_conflict_value(value) != ""


def _queue_apartment_import_conflict(
    apartment: Apartment,
    field_name: str,
    old_value: Any,
    new_value: Any,
    sheet_name: str | None,
    row_index: int,
    column_index: int | None,
) -> bool:
    """Create a pending conflict for apartment-level Excel data.

    Старые SQLite-базы могли создать sync_conflicts.task_id как NOT NULL. Поэтому
    квартирную несостыковку привязываем к первой задаче помещения, если она есть.
    Для новых баз дополнительно пишем apartment_id/field_name, чтобы кнопка
    «Принять новое» могла обновить именно поле помещения.
    """
    if _import_values_equal(old_value, new_value):
        return False
    representative_task = (
        Task.query.filter(Task.apartment_id == apartment.id, Task.project_id == apartment.project_id)
        .order_by(Task.id.asc())
        .first()
    )
    if representative_task is None:
        return False
    old_text = _format_import_conflict_value(old_value)
    new_text = _format_import_conflict_value(new_value)
    old_hash = cell_hash(old_text)
    new_hash = cell_hash(new_text)
    existing = SyncConflict.query.filter_by(
        status="pending",
        target_type="apartment",
        apartment_id=apartment.id,
        field_name=field_name,
    ).first()
    if existing:
        existing.task_id = representative_task.id
        existing.old_value = old_text
        existing.new_value = new_text
        existing.old_hash = old_hash
        existing.new_hash = new_hash
        existing.sheet_name = sheet_name
        existing.row_index = row_index
        existing.column_index = column_index
        existing.cell_address = f"{column_letter(column_index)}{row_index}" if column_index else None
        existing.field_label = APARTMENT_IMPORT_CONFLICT_LABELS.get(field_name, field_name)
        return True
    db.session.add(
        SyncConflict(
            task_id=representative_task.id,
            apartment_id=apartment.id,
            target_type="apartment",
            field_name=field_name,
            field_label=APARTMENT_IMPORT_CONFLICT_LABELS.get(field_name, field_name),
            source_type="excel",
            sheet_name=sheet_name,
            row_index=row_index,
            column_index=column_index,
            cell_address=f"{column_letter(column_index)}{row_index}" if column_index else None,
            old_value=old_text,
            new_value=new_text,
            old_hash=old_hash,
            new_hash=new_hash,
        )
    )
    return True


def _set_apartment_import_field(
    apartment: Apartment,
    field_name: str,
    new_value: Any,
    *,
    sheet_name: str | None,
    row_index: int,
    column_index: int | None = None,
    conflict_on_change: bool = True,
) -> None:
    old_value = getattr(apartment, field_name, None)
    if _import_values_equal(old_value, new_value):
        return
    # Если поле уже было заполнено на сайте/прошлой загрузке — не затираем молча,
    # а отправляем в «Несостыковки». Пустые старые значения можно заполнить сразу.
    if conflict_on_change and _has_meaningful_import_value(old_value):
        queued = _queue_apartment_import_conflict(
            apartment,
            field_name,
            old_value,
            new_value,
            sheet_name,
            row_index,
            column_index,
        )
        if queued:
            return
    setattr(apartment, field_name, new_value)


def get_or_update_apartment(
    project: Project,
    row: list[Any],
    row_index: int,
    base_mapping: dict[str, int],
    fallback_apartment_number: str | None = None,
    premise_type: str = "apartment",
    sheet_name: str | None = None,
    building: str | None = None,
    is_unsold_by_color: bool = False,
) -> Apartment:
    construction_number = normalize_number_cell(value_at(row, base_mapping.get("construction_number")))
    apartment_number = normalize_apartment_number_cell(value_at(row, base_mapping.get("apartment_number")))
    if apartment_number and apartment_number.startswith("="):
        apartment_number = None
    if premise_type == "commercial":
        apartment_number = normalize_commercial_number(apartment_number)
    apartment_number = apartment_number or apartment_number_from_construction(construction_number) or fallback_apartment_number
    sheet_part = normalize_text(sheet_name or "")
    building_part = normalize_text(building or "")
    if premise_type == "commercial":
        # Коммерции в разных корпусах имеют одинаковые номера, поэтому корпус входит в стабильный ключ.
        source_row_id = normalize_text(f"{project.id}|commercial|building-{building_part or 'unknown'}|{apartment_number or construction_number or f'row-{row_index}'}")
    elif construction_number:
        source_row_id = normalize_text(f"{project.id}|{construction_number}|{apartment_number or ''}")
    else:
        source_row_id = normalize_text(f"{project.id}|{premise_type}|{sheet_part}|row-{row_index}|{apartment_number or ''}")

    # Priority 1: exact source row identity from the latest sheet snapshot.
    apartment = Apartment.query.filter(
        Apartment.project_id == project.id,
        Apartment.source_row_id == source_row_id,
    ).first()
    # Priority 2: legacy matching by construction/apartment numbers.
    # Без строительного номера не матчим только по номеру квартиры: в Excel есть
    # повторяющиеся коммерческие помещения 1,2,3... и они начинают перетирать друг друга.
    if apartment is None and construction_number and premise_type != "commercial":
        query = Apartment.query.filter(Apartment.project_id == project.id)
        query = query.filter(Apartment.construction_number == construction_number)
        if apartment_number is None:
            query = query.filter(or_(Apartment.apartment_number.is_(None), Apartment.apartment_number == ""))
        else:
            query = query.filter(Apartment.apartment_number == apartment_number)
        apartment = query.first()
    created_apartment = apartment is None
    if apartment is None:
        apartment = Apartment(
            project_id=project.id,
            apartment_number=apartment_number,
            construction_number=construction_number,
            source_row_id=source_row_id,
        )
        db.session.add(apartment)
        db.session.flush()

    def col_for(field: str) -> int | None:
        idx = base_mapping.get(field)
        return idx + 1 if idx is not None else None

    apartment.premise_type = premise_type or "apartment"
    apartment.building = building or apartment.building

    owner_name = str(value_at(row, base_mapping.get("owner_name")) or "").strip() or None
    owner_has_real_name = bool(owner_name and not is_unsold_owner_name(owner_name))
    owner_is_unsold = bool(is_unsold_owner_name(owner_name) or (is_unsold_by_color and not owner_has_real_name))
    # Непроданные квартиры в основной таблице статистики отмечаются оранжевой
    # заливкой в колонке «№ кв. проект». Это должен быть авторитетный признак,
    # иначе счётчик на дашборде может не обновиться из-за старых конфликтов импорта.
    _set_apartment_import_field(
        apartment,
        "is_unsold",
        owner_is_unsold,
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("apartment_number") if is_unsold_by_color else col_for("owner_name"),
        conflict_on_change=False,
    )
    _set_apartment_import_field(
        apartment,
        "owner_name",
        "не продано" if owner_is_unsold else owner_name,
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("owner_name"),
        conflict_on_change=False if owner_is_unsold else not created_apartment,
    )
    _set_apartment_import_field(
        apartment,
        "phone",
        str(value_at(row, base_mapping.get("phone")) or "").strip() or None,
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("phone"),
        conflict_on_change=not created_apartment,
    )
    finishing_type = normalize_finishing_type(value_at(row, base_mapping.get("finishing_type")))
    next_finishing_type = finishing_type if premise_type == "commercial" else (finishing_type or fallback_finishing_type(project, apartment_number, apartment.id))
    _set_apartment_import_field(
        apartment,
        "finishing_type",
        next_finishing_type,
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("finishing_type"),
        conflict_on_change=not created_apartment,
    )
    _set_apartment_import_field(
        apartment,
        "entrance",
        str(value_at(row, base_mapping.get("entrance")) or "").strip() or None,
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("entrance"),
        conflict_on_change=not created_apartment,
    )
    _set_apartment_import_field(
        apartment,
        "floor",
        str(value_at(row, base_mapping.get("floor")) or "").strip() or None,
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("floor"),
        conflict_on_change=not created_apartment,
    )
    raw_inspection_value = value_at(row, base_mapping.get("inspection_date"))
    inspection_schedule = _parse_inspection_schedule_value(raw_inspection_value)
    inspection_date = inspection_schedule.date() if isinstance(inspection_schedule, datetime) else inspection_schedule
    _set_apartment_import_field(
        apartment,
        "inspection_date",
        inspection_date,
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("inspection_date"),
        conflict_on_change=not created_apartment,
    )
    schedule_marker = _inspection_schedule_marker(inspection_schedule)
    has_raw_inspection_value = raw_inspection_value is not None and str(raw_inspection_value).strip() != ""
    old_note_is_marker = _is_inspection_schedule_marker(apartment.inspection_note)
    old_note_has_comment = _has_meaningful_import_value(apartment.inspection_note) and not old_note_is_marker
    if old_note_has_comment:
        _discard_pending_inspection_schedule_conflicts(apartment)
    elif schedule_marker or (has_raw_inspection_value and old_note_is_marker):
        _set_apartment_import_field(
            apartment,
            "inspection_note",
            schedule_marker,
            sheet_name=sheet_name,
            row_index=row_index,
            column_index=col_for("inspection_date"),
            conflict_on_change=False,
        )
    _set_apartment_import_field(
        apartment,
        "reinspection_date",
        parse_date(value_at(row, base_mapping.get("reinspection_date"))),
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("reinspection_date"),
        conflict_on_change=not created_apartment,
    )

    transfer_deadline = parse_date(value_at(row, base_mapping.get("deadline_date")))
    if transfer_deadline:
        _set_apartment_import_field(
            apartment,
            "deadline_date",
            transfer_deadline,
            sheet_name=sheet_name,
            row_index=row_index,
            column_index=col_for("deadline_date"),
            conflict_on_change=not created_apartment,
        )

    app_value = value_at(row, base_mapping.get("app_signed_date"))
    app_col = col_for("app_signed_date")
    if app_value is None:
        app_value = value_at(row, base_mapping.get("deadline_date"))
        app_col = col_for("deadline_date")
    if parse_date(app_value) or _has_app_marker(app_value):
        _set_apartment_import_field(
            apartment,
            "is_app_mode",
            True,
            sheet_name=sheet_name,
            row_index=row_index,
            column_index=app_col,
            conflict_on_change=not created_apartment,
        )
        signed_date = parse_date(app_value)
        if signed_date:
            _set_apartment_import_field(
                apartment,
                "deadline_date",
                signed_date,
                sheet_name=sheet_name,
                row_index=row_index,
                column_index=app_col,
                conflict_on_change=not created_apartment,
            )

    if base_mapping.get("remark_deadline_date") is not None:
        remark_deadline_raw = value_at(row, base_mapping.get("remark_deadline_date"))
        snapshot_fields = ["is_app_mode", "app_deadline_date", "remark_deadline_date", "app_deadline_raw", "app_deadline_status", "avr_status", "avr_signed_date"]
        old_snapshot = {field: getattr(apartment, field, None) for field in snapshot_fields}
        apply_app_deadline_logic(apartment, remark_deadline_raw)
        if not created_apartment:
            for field in snapshot_fields:
                next_value = getattr(apartment, field, None)
                old_value = old_snapshot[field]
                if _has_meaningful_import_value(old_value) and not _import_values_equal(old_value, next_value):
                    queued = _queue_apartment_import_conflict(
                        apartment,
                        field,
                        old_value,
                        next_value,
                        sheet_name,
                        row_index,
                        col_for("remark_deadline_date"),
                    )
                    if queued:
                        setattr(apartment, field, old_value)

    _set_apartment_import_field(
        apartment,
        "comment",
        str(value_at(row, base_mapping.get("comment")) or "").strip() or None,
        sheet_name=sheet_name,
        row_index=row_index,
        column_index=col_for("comment"),
        conflict_on_change=not created_apartment,
    )
    apartment.source_row_id = source_row_id
    db.session.flush()
    return apartment


def get_or_update_work_point(point_number: str, header: str, sheet_name: str, column_index: int) -> WorkPoint:
    point = WorkPoint.query.filter_by(point_number=point_number, source_sheet_name=sheet_name).first()
    if point is None:
        point = WorkPoint(point_number=point_number, source_sheet_name=sheet_name)
        db.session.add(point)
    point.original_column_name = header
    point.short_name = header
    point.source_column_index = column_index
    point.is_active = True
    db.session.flush()
    return point


def mark_task_done(task: Task, user_id: int | None = None):
    old = task.status
    task.status = STATUS_DONE
    task.is_done = True
    task.completed_date = task.completed_date or datetime.utcnow()
    log_change(task, "status_change", "status", old, STATUS_DONE, user_id=user_id)
    db.session.commit()
    return task


def change_task_status(task: Task, new_status: str, user_id: int | None = None, *, commit: bool = True):
    old_status = task.status
    if old_status == new_status:
        return task
    task.status = new_status
    task.is_done = new_status in DONE_STATUSES
    if task.is_done:
        task.completed_date = task.completed_date or datetime.utcnow()
    elif old_status in DONE_STATUSES:
        task.completed_date = None
    task.manually_edited = True
    log_change(task, "status_change", "status", old_status, new_status, user_id=user_id)
    if commit:
        db.session.commit()
    return task


def upsert_task_from_cell(
    project: Project,
    apartment: Apartment,
    legacy_construction_number: str,
    legacy_apartment_number: str,
    work_point: WorkPoint,
    remark_text: str,
    source_cell_value: str,
    sheet_name: str,
    row_index: int,
    column_index: int,
    source_cell_address: str,
    sync_time: datetime,
    source_cell_is_struck: bool = False,
) -> tuple[Task, bool]:
    new_hash = cell_hash(source_cell_value)

    task = None
    if sheet_name and row_index and column_index:
        task = Task.query.filter_by(
            project_id=project.id,
            source_sheet_name=sheet_name,
            source_row_index=row_index,
            source_column_index=column_index,
        ).first()
    uid_construction = apartment.construction_number or ""
    uid_apartment = apartment.apartment_number or ""
    if (apartment.premise_type or "apartment") == "commercial":
        uid_construction = apartment.source_row_id or apartment.construction_number or ""
        uid_apartment = apartment.apartment_number or ""
    source_uid = build_task_uid(
        project.name,
        uid_construction,
        uid_apartment,
        work_point.point_number,
        work_point.display_name,
        remark_text,
    )
    if task is None:
        task = Task.query.filter_by(source_uid=source_uid).first()
    if task is None and (legacy_construction_number or legacy_apartment_number):
        legacy_uid = build_task_uid(
            project.name,
            legacy_construction_number or "",
            legacy_apartment_number or "",
            work_point.point_number,
            work_point.display_name,
            remark_text,
        )
        task = Task.query.filter_by(source_uid=legacy_uid).first()
        if task is not None:
            task.source_uid = source_uid
    if task is None and legacy_construction_number:
        derived_apartment = apartment_number_from_construction(legacy_construction_number)
        if derived_apartment:
            legacy_uid2 = build_task_uid(
                project.name,
                legacy_construction_number or "",
                derived_apartment or "",
                work_point.point_number,
                work_point.display_name,
                remark_text,
            )
            task = Task.query.filter_by(source_uid=legacy_uid2).first()
            if task is not None:
                task.source_uid = source_uid
    created = task is None
    if created:
        task = Task(
            source_uid=source_uid,
            project_id=project.id,
            apartment_id=apartment.id,
            work_point_id=work_point.id,
            status=STATUS_NOT_STARTED,
            is_done=False,
            title=f"Пункт {work_point.point_number}: {work_point.display_name}",
        )
        db.session.add(task)
    task.apartment_id = apartment.id
    task.work_point_id = work_point.id
    task.title = f"Пункт {work_point.point_number}: {work_point.display_name}"
    # Любое изменение уже известной ячейки Excel теперь попадает в «Несостыковки».
    # Раньше конфликт создавался только после ручной правки на сайте, из-за этого
    # изменения дат/действий/текста из новой таблицы могли молча перетираться.
    if task.source_hash and task.source_hash != new_hash:
        existing = _pending_text_sync_conflict(task.id)
        if existing is None:
            db.session.add(
                SyncConflict(
                    task_id=task.id,
                    target_type="task",
                    field_name="source_cell_value",
                    field_label="Ячейка замечания",
                    source_type="excel",
                    sheet_name=sheet_name,
                    row_index=row_index,
                    column_index=column_index,
                    cell_address=source_cell_address,
                    old_value=task.source_cell_value,
                    new_value=source_cell_value,
                    old_hash=task.source_hash,
                    new_hash=new_hash,
                )
            )
        else:
            existing.new_value = source_cell_value
            existing.new_hash = new_hash
            existing.sheet_name = sheet_name
            existing.row_index = row_index
            existing.column_index = column_index
            existing.cell_address = source_cell_address
    else:
        if not task.manually_edited or not task.description:
            task.description = remark_text
        task.source_cell_value = source_cell_value
        task.source_hash = new_hash
    task.source_sheet_name = sheet_name
    task.source_row_index = row_index
    task.source_column_index = column_index
    task.source_cell_address = source_cell_address
    task.source_hash = task.source_hash or new_hash
    task.is_missing_in_latest_sync = False
    task.last_seen_at = sync_time
    # Новая таблица может автоматически назначить статус только замечанию,
    # которое в CRM всё ещё находится в статусе «Не выполнено». Уже выставленные
    # статусы являются приоритетными и импортом не перезаписываются.
    auto_status = detect_status_marker(remark_text)
    if source_cell_is_struck and auto_status is None:
        auto_status = STATUS_DONE
    if should_auto_finishers(apartment, work_point):
        auto_status = STATUS_FINISHERS
    if auto_status and task.status == STATUS_NOT_STARTED:
        old_status = task.status
        task.status = auto_status
        task.is_done = auto_status in DONE_STATUSES
        task.completed_date = task.completed_date or sync_time if task.is_done else None
        if old_status != auto_status:
            log_change(task, "status_change", "status", old_status, auto_status, user_id=None)
    db.session.flush()
    return task, created


def sync_rows(
    rows: list[list[Any]],
    sheet_name: str,
    project_name: str = "100 Квартал 7 очередь",
    source_name: str | None = None,
    struck_cells: set[tuple[int, int]] | None = None,
    unsold_color_cells: set[tuple[int, int]] | None = None,
    mark_missing: bool = True,
) -> dict[str, int | set[str]]:
    ensure_default_categories()
    project = get_or_create_project(project_name)
    result = SyncResult(seen_uids=set())
    if not rows:
        return result.as_dict() | {"seen_uids": set()}

    header_index = find_header_row(rows)
    if header_index > 0 and is_index_number_row(rows[header_index]):
        header_index -= 1
    headers = normalize_header_row(rows[header_index])
    if header_index > 0:
        headers = merge_header_rows(rows[header_index - 1], rows[header_index])
    base_mapping = map_base_columns(headers)
    point_columns = map_work_point_columns(headers, base_mapping)

    sync_time = datetime.utcnow()

    default_premise_type = "commercial" if "коммер" in (sheet_name or "").strip().lower() else "apartment"
    premise_type = default_premise_type
    current_building: str | None = None
    commercial_numbers_in_building: set[str] = set()
    if premise_type == "commercial" and not getattr(project, "has_commercial", True):
        return result.as_dict() | {"seen_uids": set()}
    if premise_type == "apartment" and not getattr(project, "has_apartments", True):
        return result.as_dict() | {"seen_uids": set()}

    data_start = header_index + 1
    if data_start < len(rows) and is_index_number_row(rows[data_start]):
        index_row = rows[data_start]
        base_indexes = set(base_mapping.values())
        indexed_points: dict[int, str] = {}
        for col_idx, raw in enumerate(index_row):
            if col_idx in base_indexes:
                continue
            point_number = _indexed_visible_point_number(raw)
            if point_number:
                header = headers[col_idx] if col_idx < len(headers) else ""
                if header:
                    indexed_points[col_idx] = f"{point_number}. {header}"
        if indexed_points:
            point_columns = indexed_points
        data_start += 1

    point_columns = select_primary_work_point_columns(headers, point_columns)
    if point_columns:
        anchored_mapping = map_base_columns(headers, anchor_before_col=min(point_columns))
        if anchored_mapping.get("apartment_number") is not None or anchored_mapping.get("construction_number") is not None:
            base_mapping = anchored_mapping
            base_indexes = set(base_mapping.values())
            point_columns = {idx: header for idx, header in point_columns.items() if idx not in base_indexes}
    if not point_columns or (base_mapping.get("apartment_number") is None and base_mapping.get("construction_number") is None):
        return result.as_dict() | {"seen_uids": set()}

    for row_zero_idx, row in enumerate(rows[data_start:], start=data_start + 1):
        if not any(str(c or "").strip() for c in row):
            continue
        if is_index_number_row(row):
            continue

        section_marker = is_premise_section_marker(row)
        if section_marker:
            premise_type = section_marker
            if premise_type == "commercial":
                current_building = current_building or "1"
                commercial_numbers_in_building = set()
            continue

        building_marker = normalize_building_marker(value_at(row, 0))
        if building_marker:
            current_building = building_marker
            commercial_numbers_in_building = set()
            continue

        current_premise_type = premise_type
        if current_premise_type == "commercial" and not getattr(project, "has_commercial", True):
            continue
        if current_premise_type == "apartment" and not getattr(project, "has_apartments", True):
            continue

        raw_apartment_number = normalize_apartment_number_cell(value_at(row, base_mapping.get("apartment_number")))
        raw_construction_number = normalize_number_cell(value_at(row, base_mapping.get("construction_number")))
        if current_premise_type == "apartment":
            apartment_number_looks_valid = looks_like_apartment_identifier(raw_apartment_number)
            construction_number_looks_valid = looks_like_apartment_identifier(raw_construction_number)
            if (
                not raw_construction_number
                or is_service_premise_text(raw_apartment_number)
                or (not construction_number_looks_valid and not apartment_number_looks_valid)
            ):
                continue
        if current_premise_type == "commercial":
            raw_apartment_number = normalize_commercial_number(raw_apartment_number)
            if current_building is None:
                current_building = "1"
            # В основной вкладке коммерции идут двумя блоками 1..9 и 1..8 без строки "2 корпус".
            # Когда номер повторяется, начинаем следующий корпус.
            if raw_apartment_number and raw_apartment_number in commercial_numbers_in_building:
                try:
                    current_building = str(int(current_building or "1") + 1)
                except ValueError:
                    current_building = "2"
                commercial_numbers_in_building = set()
            if raw_apartment_number:
                commercial_numbers_in_building.add(raw_apartment_number)

        unsold_marker_columns = [
            base_mapping.get("apartment_number"),
            base_mapping.get("construction_number"),
            base_mapping.get("owner_name"),
            base_mapping.get("phone"),
            base_mapping.get("finishing_type"),
        ]
        unsold_by_number_color = bool(
            unsold_color_cells
            and any(
                col_zero_idx is not None and (row_zero_idx, col_zero_idx + 1) in unsold_color_cells
                for col_zero_idx in unsold_marker_columns
            )
        )
        apartment = get_or_update_apartment(
            project,
            row,
            row_zero_idx,
            base_mapping,
            fallback_apartment_number=str(row_zero_idx),
            premise_type=current_premise_type,
            sheet_name=sheet_name,
            building=current_building if current_premise_type == "commercial" else None,
            is_unsold_by_color=unsold_by_number_color,
        )
        if not (apartment.apartment_number or apartment.construction_number):
            continue
        legacy_apartment_number = str(value_at(row, base_mapping.get("apartment_number")) or "").strip()
        legacy_construction_number = str(value_at(row, base_mapping.get("construction_number")) or "").strip()
        for col_zero_idx, header in point_columns.items():
            cell_value = value_at(row, col_zero_idx)
            point_number = extract_point_number(header, col_zero_idx + 1)
            work_point = get_or_update_work_point(point_number, header, sheet_name, col_zero_idx + 1)
            cell_text = str(cell_value or "").strip()
            if not cell_text:
                # If a previously existing remark disappeared from the source cell,
                # register a conflict so user can decide what to do.
                existing_task = Task.query.filter_by(
                    project_id=project.id,
                    source_sheet_name=sheet_name,
                    source_row_index=row_zero_idx,
                    source_column_index=col_zero_idx + 1,
                ).first()
                if (
                    existing_task
                    and existing_task.source_hash
                    and existing_task.source_cell_value
                    and not existing_task.manually_edited
                ):
                    new_hash = cell_hash("")
                    if existing_task.source_hash != new_hash:
                        existing_conflict = _pending_text_sync_conflict(existing_task.id)
                        if existing_conflict is None:
                            db.session.add(
                                SyncConflict(
                                    task_id=existing_task.id,
                                    target_type="task",
                                    field_name="source_cell_value",
                                    field_label="Ячейка замечания",
                                    source_type="excel",
                                    sheet_name=sheet_name,
                                    row_index=row_zero_idx,
                                    column_index=col_zero_idx + 1,
                                    cell_address=f"{column_letter(col_zero_idx + 1)}{row_zero_idx}",
                                    old_value=existing_task.source_cell_value,
                                    new_value="",
                                    old_hash=existing_task.source_hash,
                                    new_hash=new_hash,
                                )
                            )
                continue

            remarks = split_cell_remarks(cell_value)
            if not remarks:
                continue
            for remark in remarks:
                cell_address = f"{column_letter(col_zero_idx + 1)}{row_zero_idx}"
                cell_is_struck = bool(struck_cells and (row_zero_idx, col_zero_idx + 1) in struck_cells)
                task, created = upsert_task_from_cell(
                    project=project,
                    apartment=apartment,
                    legacy_construction_number=legacy_construction_number,
                    legacy_apartment_number=legacy_apartment_number,
                    work_point=work_point,
                    remark_text=remark,
                    source_cell_value=str(cell_value or ""),
                    sheet_name=sheet_name,
                    row_index=row_zero_idx,
                    column_index=col_zero_idx + 1,
                    source_cell_address=cell_address,
                    sync_time=sync_time,
                    source_cell_is_struck=cell_is_struck,
                )
                result.seen_uids.add(task.source_uid)
                if created:
                    result.created_count += 1
                    log_change(task, "created_from_sync", None, None, source_name or sheet_name)
                else:
                    result.updated_count += 1
    if mark_missing:
        missing_query = Task.query.filter(Task.project_id == project.id)
        missing_query = missing_query.filter(Task.work_point.has(WorkPoint.point_number.in_(VISIBLE_WORK_POINT_NUMBERS)))
        if result.seen_uids:
            missing_query = missing_query.filter(~Task.source_uid.in_(result.seen_uids))
            missing_tasks = missing_query.all()
            for task in missing_tasks:
                if not task.is_missing_in_latest_sync:
                    task.is_missing_in_latest_sync = True
                    log_change(task, "missing_in_latest_sync", "is_missing_in_latest_sync", False, True)
                result.missing_count += 1
    set_setting("last_sync_at", sync_time.isoformat())
    set_setting("last_sync_source", source_name or sheet_name)
    apply_default_point_mapping(commit=False)
    db.session.commit()
    return result.as_dict() | {"seen_uids": result.seen_uids}


def column_letter(n: int) -> str:
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def build_task_query(params, category_id: int | None = None, project_id: int | None = None):
    query = Task.query.join(Apartment).join(WorkPoint).outerjoin(User, Task.responsible_id == User.id)
    if project_id:
        query = query.filter(Task.project_id == project_id)

    category = db.session.get(WorkCategory, category_id) if category_id else None
    category_name = (category.name or "").strip().lower() if category else ""

    if category and category_name != "все":
        point_ids = [p.id for p in category.work_points]
        query = query.filter(Task.work_point_id.in_(point_ids or [-1]))
    else:
        # Вкладка "Все" должна показывать только рабочие пункты 10-22.
        query = query.filter(WorkPoint.point_number.in_(MAIN_WORK_POINT_NUMBERS))

    apartment_number = (params.get("apartment_number") or "").strip()
    if apartment_number:
        if "-" in apartment_number:
            query = query.filter(Apartment.construction_number == apartment_number)
        else:
            query = query.filter(Apartment.apartment_number == apartment_number)

    q = (params.get("q") or "").strip()
    premise_selectors: list[tuple[str, str]] = []
    if q:
        premise_selectors, tail_query = parse_multi_premise_search(q)
        if premise_selectors:
            selector_clauses = [premise_selector_clause(selector) for selector in premise_selectors]
            selector_clauses = [clause for clause in selector_clauses if clause is not None]
            if selector_clauses:
                query = query.filter(or_(*selector_clauses))
            if tail_query:
                like = f"%{tail_query}%"
                query = query.filter(
                    or_(
                        Apartment.apartment_number.ilike(like),
                        Apartment.construction_number.ilike(like),
                        Apartment.owner_name.ilike(like),
                        Apartment.phone.ilike(like),
                        Task.description.ilike(like),
                        Task.source_cell_value.ilike(like),
                        WorkPoint.point_number.ilike(like),
                        WorkPoint.short_name.ilike(like),
                        User.full_name.ilike(like),
                        User.username.ilike(like),
                    )
                )
        else:
            search_mode, search_value = detect_search_mode(q)
            if search_mode == "commercial_pair":
                number, _, building = search_value.partition("|")
                query = query.filter(
                    Apartment.premise_type == "commercial",
                    Apartment.apartment_number == number,
                    Apartment.building == building,
                )
            elif search_mode == "construction_number":
                query = query.filter(Apartment.construction_number == search_value)
            elif search_mode == "premise_number_or_building":
                query = query.filter(
                    or_(
                        Apartment.apartment_number == search_value,
                        (Apartment.premise_type == "commercial") & (Apartment.building == search_value),
                    )
                )
            elif search_mode == "premise_number":
                query = query.filter(Apartment.apartment_number == search_value)
            else:
                like = f"%{search_value}%"
                query = query.filter(
                    or_(
                        Apartment.apartment_number.ilike(like),
                        Apartment.construction_number.ilike(like),
                        Apartment.owner_name.ilike(like),
                        Apartment.phone.ilike(like),
                        Task.description.ilike(like),
                        Task.source_cell_value.ilike(like),
                        WorkPoint.point_number.ilike(like),
                        WorkPoint.short_name.ilike(like),
                        User.full_name.ilike(like),
                        User.username.ilike(like),
                    )
                )

    status = params.get("status")
    if status != "missing":
        query = query.filter(Task.is_missing_in_latest_sync.is_(False))
    if status != "archived":
        query = query.filter(Task.is_archived.is_(False))

    today_value = date.today()
    expiring_until = today_value + timedelta(days=15)

    if status:
        if status == "not_done":
            query = query.filter(Task.is_done.is_(False))
        elif status == "missing":
            query = query.filter(Task.is_missing_in_latest_sync.is_(True))
        elif status == "archived":
            query = query.filter(Task.is_archived.is_(True))
        elif status == "manual":
            query = query.filter(Task.manually_edited.is_(True))
        elif status == "deadline_expired":
            query = query.filter(Apartment.app_deadline_date.isnot(None), Apartment.app_deadline_date < today_value)
        elif status == "deadline_expiring":
            query = query.filter(Apartment.app_deadline_date.isnot(None), Apartment.app_deadline_date >= today_value, Apartment.app_deadline_date <= expiring_until)
        elif status == "not_started":
            query = query.filter(Task.is_done.is_(False))
        elif status == "done":
            query = query.filter(Task.status == STATUS_DONE)
        else:
            query = query.filter(Task.status == status)

    acceptance_status = (params.get("acceptance_status") or "").strip()
    if acceptance_status == "accepted":
        query = query.filter(Apartment.is_app_mode.is_(True))
    elif acceptance_status == "waiting":
        query = query.filter(Apartment.is_app_mode.is_(False))

    responsible = params.get("responsible_id")
    if responsible:
        query = query.filter(Task.responsible_id == int(responsible))

    point = params.get("point")
    if point:
        query = query.filter(WorkPoint.point_number == point)

    finishing_type = params.get("finishing_type")
    if finishing_type:
        query = query.filter(Apartment.finishing_type == finishing_type)
    finishing_groups = set(get_multi_param_values(params, "finishing_group"))
    if finishing_groups:
        white_clause = or_(Apartment.finishing_type.like("%Бел%"), Apartment.finishing_type.like("%бел%"))
        none_clause = or_(Apartment.finishing_type.is_(None), func.trim(func.coalesce(Apartment.finishing_type, "")) == "")
        clean_clause = and_(~white_clause, ~none_clause)
        finishing_clauses = []
        if "white" in finishing_groups:
            finishing_clauses.append(white_clause)
        if "clean" in finishing_groups:
            finishing_clauses.append(clean_clause)
        if "none" in finishing_groups:
            finishing_clauses.append(none_clause)
        if finishing_clauses:
            query = query.filter(or_(*finishing_clauses))

    sort = params.get("sort") or "apartment"
    if status in {"deadline_expired", "deadline_expiring"} and sort == "apartment":
        sort = "status"
    if category_name == "доп.соглашение" and sort not in {"apartment", "status"}:
        sort = "apartment"

    done_last = Task.is_done.asc()
    premise_order_rank = None
    if premise_selectors:
        rank_clauses = []
        for index, selector in enumerate(premise_selectors):
            clause = premise_selector_clause(selector)
            if clause is not None:
                rank_clauses.append((clause, index))
        if rank_clauses:
            premise_order_rank = case(*rank_clauses, else_=len(rank_clauses))
    deadline_rank = case(
        (Apartment.app_deadline_date.is_(None), 3),
        (Apartment.app_deadline_date < today_value, 0),
        (Apartment.app_deadline_date <= expiring_until, 1),
        else_=2,
    )

    def ordered(*parts):
        if premise_order_rank is None:
            return parts
        return (done_last, premise_order_rank.asc(), *parts[1:]) if parts and parts[0] is done_last else (premise_order_rank.asc(), *parts)

    if sort == "apartment":
        query = query.order_by(*ordered(done_last, cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc(), WorkPoint.point_number.asc()))
    elif sort == "construction_number":
        query = query.order_by(*ordered(done_last, Apartment.construction_number.asc(), WorkPoint.point_number.asc()))
    elif sort == "owner":
        query = query.order_by(*ordered(done_last, Apartment.owner_name.asc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc()))
    elif sort == "finishing_type":
        query = query.order_by(*ordered(done_last, Apartment.finishing_type.asc().nullslast(), Apartment.apartment_number.asc()))
    elif sort == "point":
        query = query.order_by(*ordered(done_last, WorkPoint.point_number.asc(), Apartment.apartment_number.asc()))
    elif sort == "status":
        query = query.order_by(*ordered(done_last, deadline_rank.asc(), Apartment.app_deadline_date.asc().nullslast(), Task.status.asc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc()))
    elif sort == "mode":
        query = query.order_by(*ordered(done_last, Apartment.is_app_mode.asc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc()))
    elif sort == "priority":
        query = query.order_by(*ordered(done_last, Task.priority.desc(), Task.updated_at.desc()))
    elif sort == "planned_old":
        query = query.order_by(*ordered(done_last, Task.planned_date.asc().nullslast(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc()))
    elif sort == "planned_new":
        query = query.order_by(*ordered(done_last, Task.planned_date.desc().nullslast(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc()))
    elif sort == "done_first":
        query = query.order_by(*ordered(done_last, Task.updated_at.desc()))
    else:
        query = query.order_by(*ordered(done_last, Task.updated_at.desc()))
    return query


def _base_dashboard_task_query(
    project_id: int | None = None,
    *,
    include_all_completed_statuses: bool = False,
):
    query = Task.query.join(WorkPoint).filter(
        WorkPoint.point_number.in_(MAIN_WORK_POINT_NUMBERS),
        Task.is_archived.is_(False),
        Task.is_missing_in_latest_sync.is_(False),
    )
    if not include_all_completed_statuses:
        query = query.filter(Task.status.notin_([STATUS_FINISHERS, STATUS_CONTRACTOR]))
    if project_id:
        query = query.filter(Task.project_id == project_id)
    return query


def _premise_group_key(apartment: Apartment) -> str:
    premise_type = apartment.premise_type or "apartment"
    identity = apartment.apartment_number or apartment.construction_number or apartment.source_row_id or str(apartment.id)
    identity = str(identity).strip() or str(apartment.id)
    if premise_type == "commercial":
        identity = normalize_commercial_number(identity) or identity
        building = str(getattr(apartment, "building", "") or "").strip()
        if building and identity:
            return f"{premise_type}:building:{building}:num:{identity}"
        source = str(getattr(apartment, "source_row_id", "") or "").strip() or str(apartment.id)
        return f"{premise_type}:building:{building}:num:{identity}:src:{source}"
    return f"{premise_type}:{identity}"


def _premise_rows_from_query(query):
    return query.with_entities(
        Apartment.id,
        Apartment.premise_type,
        Apartment.apartment_number,
        Apartment.construction_number,
        Apartment.source_row_id,
        Apartment.building,
        Apartment.owner_name,
        Apartment.is_unsold,
        Apartment.phone,
        Apartment.finishing_type,
        Apartment.is_app_mode,
        Apartment.first_inspection_present,
        Apartment.first_inspection_date,
        Apartment.inspection_note,
    ).all()


def _row_to_premise(row):
    class Obj:
        pass
    apartment = Obj()
    apartment.id = row.id
    apartment.premise_type = row.premise_type
    apartment.apartment_number = row.apartment_number
    apartment.construction_number = row.construction_number
    apartment.source_row_id = row.source_row_id
    apartment.building = getattr(row, "building", None)
    apartment.owner_name = getattr(row, "owner_name", None)
    apartment.is_unsold = bool(getattr(row, "is_unsold", False))
    apartment.finishing_type = getattr(row, "finishing_type", None)
    return apartment


def _distinct_apartment_count(query):
    return len({_premise_group_key(_row_to_premise(row)) for row in _premise_rows_from_query(query)})


def _grouped_premise_rows(query) -> dict[str, list]:
    groups: dict[str, list] = {}
    for row in _premise_rows_from_query(query):
        if _row_premise_type(row) == "apartment" and is_service_premise_text(getattr(row, "apartment_number", None) or getattr(row, "construction_number", None)):
            continue
        groups.setdefault(_premise_group_key(_row_to_premise(row)), []).append(row)
    return groups



def _row_has_contact(row) -> bool:
    owner = str(getattr(row, "owner_name", None) or "").strip()
    phone = str(getattr(row, "phone", None) or "").strip()
    return bool(owner or phone)


def _group_is_unsold(rows: list) -> bool:
    # Непроданное помещение считается только по явному признаку.
    # Если в ФИО указан реальный собственник, помещение не считаем непроданным
    # даже при старой/случайной оранжевой отметке.
    return bool(rows) and any(is_apartment_unsold(row) for row in rows)


def _group_is_accepted(rows: list) -> bool:
    return any(bool(getattr(row, "is_app_mode", False)) for row in rows)


def _row_premise_type(row) -> str:
    return (getattr(row, "premise_type", None) or "apartment").strip() or "apartment"


def _has_first_inspection(rows: list) -> bool:
    # The transfer statistics import is the source of truth: red/yellow fill in
    # "Дата осмотра" stores False, every other fill stores True. Duplicate source
    # rows represent one premise, so one positive row is enough for the group.
    return any(bool(getattr(row, "first_inspection_present", False)) for row in rows)


def _finishing_bucket(value: str | None) -> str:
    finishing = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    if not finishing:
        return "unknown"
    if "бел" in finishing:
        return "white"
    return "clean"


def dashboard_stats(
    project_id: int | None = None,
    *,
    include_all_completed_statuses: bool = False,
):
    task_query = _base_dashboard_task_query(
        project_id,
        include_all_completed_statuses=include_all_completed_statuses,
    )
    apartment_query = Apartment.query.filter(Apartment.apartment_number.isnot(None), Apartment.apartment_number != "")
    if project_id:
        apartment_query = apartment_query.filter(Apartment.project_id == project_id)

    total_tasks = task_query.count()
    completed_statuses = DONE_STATUSES if include_all_completed_statuses else {STATUS_DONE}
    done = task_query.filter(Task.status.in_(completed_statuses)).count()

    grouped_rows = _grouped_premise_rows(apartment_query)
    total_apartments = len(grouped_rows)
    apartment_count = sum(1 for rows in grouped_rows.values() if rows and _row_premise_type(rows[0]) == "apartment")
    commercial_count = sum(1 for rows in grouped_rows.values() if rows and _row_premise_type(rows[0]) == "commercial")

    accepted = sum(
        1
        for rows in grouped_rows.values()
        if rows and _row_premise_type(rows[0]) == "apartment" and _group_is_accepted(rows)
    )
    unsold_apartment_count = sum(
        1
        for rows in grouped_rows.values()
        if rows and _row_premise_type(rows[0]) == "apartment" and _group_is_unsold(rows)
    )
    unsold_commercial_count = sum(
        1
        for rows in grouped_rows.values()
        if rows and _row_premise_type(rows[0]) == "commercial" and _group_is_unsold(rows)
    )
    unsold = unsold_apartment_count + unsold_commercial_count
    not_accepted = max(total_apartments - accepted - unsold, 0)

    inspected = sum(1 for rows in grouped_rows.values() if _has_first_inspection(rows))
    not_inspected = max(total_apartments - inspected, 0)
    white = 0
    clean = 0
    unknown_finishing = 0
    for rows in grouped_rows.values():
        if not rows or _row_premise_type(rows[0]) != "apartment":
            continue
        buckets = {_finishing_bucket(getattr(row, "finishing_type", None)) for row in rows}
        if "white" in buckets:
            white += 1
        elif "clean" in buckets:
            clean += 1
        else:
            unknown_finishing += 1

    return {
        "apartments": total_apartments,
        "apartment_count": apartment_count,
        "commercial_count": commercial_count,
        "tasks": total_tasks,
        "done": done,
        "not_done": total_tasks - done,
        "in_progress": task_query.filter(Task.status == "in_progress").count(),
        "problem": task_query.filter(Task.status == "problem").count(),
        "missing": Task.query.filter(Task.project_id == project_id, Task.is_missing_in_latest_sync.is_(True)).count() if project_id else Task.query.filter(Task.is_missing_in_latest_sync.is_(True)).count(),
        "percent": round((done / total_tasks * 100), 1) if total_tasks else 0,
        "accepted": accepted,
        "unsold": unsold,
        "unsold_apartment_count": unsold_apartment_count,
        "unsold_commercial_count": unsold_commercial_count,
        "not_accepted": not_accepted,
        "inspected": inspected,
        "not_inspected": not_inspected,
        "clean_apartments": clean,
        "white_apartments": white,
        "unknown_finishing_apartments": unknown_finishing,
        "last_sync_at": get_setting("last_sync_at", "—"),
        "last_sync_source": get_setting("last_sync_source", "—"),
    }


def category_stats(
    project_id: int | None = None,
    *,
    include_all_completed_statuses: bool = False,
):
    rows = []
    for category in WorkCategory.query.filter_by(is_active=True).order_by(WorkCategory.sort_order.asc()).all():
        category_name = (category.name or "").strip().lower()
        if category_name in {"все", "доп.соглашение"}:
            continue
        ids = [p.id for p in category.work_points if p.point_number in MAIN_WORK_POINT_NUMBERS]
        query = Task.query.filter(
            Task.work_point_id.in_(ids or [-1]),
            Task.is_archived.is_(False),
            Task.is_missing_in_latest_sync.is_(False),
        )
        if not include_all_completed_statuses:
            query = query.filter(Task.status.notin_([STATUS_FINISHERS, STATUS_CONTRACTOR]))
        if project_id:
            query = query.filter(Task.project_id == project_id)
        total = query.count()
        completed_statuses = DONE_STATUSES if include_all_completed_statuses else {STATUS_DONE}
        done = query.filter(Task.status.in_(completed_statuses)).count()
        rows.append({"category": category, "total": total, "done": done, "left": total - done})
    return rows
