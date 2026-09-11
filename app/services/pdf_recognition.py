from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from io import BytesIO
import re
from typing import BinaryIO

from app.services.task_service import VISIBLE_WORK_POINT_NUMBERS, parse_date
from app.services.uid_service import normalize_text


NO_REMARK_MARKERS = (
    "замечания отсутствуют",
    "замечаний отсутствует",
    "замечаний нет",
    "без замечаний",
)

PDF_POINT_NUMBER_RE = r"(?:[1-9]|1[0-9]|2[0-4])"
POINT_LINE_RE = re.compile(rf"^\s*(?:п\.?|пункт)?\s*({PDF_POINT_NUMBER_RE})(?:[\).:\-]|\s+)(?!\d)(.*)$", re.IGNORECASE)
APARTMENT_RE = re.compile(r"(?:квартира|кв\.?|помещение)\s*(?:№|N|No|номер)?\s*([0-9]+[A-Za-zА-Яа-яЁё/-]*)", re.IGNORECASE)
DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
POINT_SPLIT_RE = re.compile(rf"(?<!\n)(?:\s+|(?<=[\.:;]))((?:п\.?|пункт)?\s*{PDF_POINT_NUMBER_RE}(?:[\).:\-]))(?!\d)", re.IGNORECASE)
COMPACT_DATE_RE = re.compile(r"дата[:\-]*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", re.IGNORECASE)
COMPACT_APARTMENT_RE = re.compile(r"^([0-9]+[a-zа-яё/-]*)", re.IGNORECASE)
POINT_HEADER_RE = re.compile(r"^\s*([^:\n]{1,80}):\s*(.*)$", re.DOTALL)
SIGNATURE_TAIL_RE = re.compile(r"\bинженер\s+технического\s+надзора\b.*$", re.IGNORECASE | re.DOTALL)
_OCR_ENGINE = None
_OCR_ENGINE_ERROR: str | None = None
TEMPLATE_MARKERS = (
    "названиежк",
    "номерквартиры",
    "фиоклиента",
    "выявленныенедостатки",
)
PROJECT_STOP_MARKERS = (
    "номерквартиры",
    "фиоклиента",
    "телефон",
    "выявленныенедостатки",
    "город",
    "дата",
)
APARTMENT_STOP_MARKERS = (
    "фиоклиента",
    "телефон",
    "выявленныенедостатки",
    "город",
    "дата",
)
LATIN_LOOKALIKES = str.maketrans(
    {
        "a": "а",
        "c": "с",
        "e": "е",
        "h": "н",
        "k": "к",
        "m": "м",
        "o": "о",
        "p": "р",
        "t": "т",
        "x": "х",
        "y": "у",
    }
)
PDF_POINT_TO_WORK_POINT = {
    "1": "11",
    "2": "13",
    "3": "20",
    "4": "21",
    "5": "10",
    "6": "19",
    "7": "16",
    "8": "18",
    "9": "19",
    "10": "11",
    "11": "22",
    "12": "22",
}
PDF_POINT_TITLE_ALIASES = (
    ("вентиляц", "10"),
    ("стен", "11"),
    ("потолк", "11"),
    ("пол", "13"),
    ("входн", "20"),
    ("двер", "20"),
    ("электрик", "21"),
    ("радиатор", "19"),
    ("отоплен", "19"),
    ("гви", "19"),
    ("хв", "19"),
    ("окн", "16"),
    ("пвх", "16"),
    ("балкон", "18"),
    ("лоджи", "18"),
    ("тепловиз", "22"),
    ("проч", "22"),
)


@dataclass
class PdfRemarkPreview:
    point_number: str
    description: str
    active: bool = True


@dataclass
class PdfActPreview:
    filename: str
    template_ok: bool
    project_ok: bool
    project_prefix: str
    project_name: str = ""
    apartment_number: str | None = None
    inspection_date: date | None = None
    remarks: list[PdfRemarkPreview] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_ocr: bool = False


def is_no_remark_text(value: str | None) -> bool:
    text = normalize_text(value or "").replace("ё", "е")
    return bool(text) and any(marker in text for marker in NO_REMARK_MARKERS)


def _project_prefix(project_name: str | None) -> str:
    text = normalize_text(project_name or "").replace("ё", "е")
    letters = "".join(ch for ch in text if ch.isalnum())
    return letters[:3]


def _clean_recognized_text(text: str | None) -> str:
    value = str(text or "")
    value = value.replace("\r", "\n").replace("\x0c", "\n").replace("\xa0", " ")
    value = value.replace("No ", "№ ").replace("N ", "№ ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = POINT_SPLIT_RE.sub(r"\n\1", value)
    return value.strip()


def _compact_normalized_text(text: str | None) -> str:
    value = normalize_text(text or "").replace("ё", "е")
    value = value.translate(LATIN_LOOKALIKES)
    return re.sub(r"\s+", "", value)


def _extract_compact_value(compact_text: str, marker: str, stop_markers: tuple[str, ...], max_length: int = 120) -> str | None:
    marker_index = compact_text.find(marker)
    if marker_index < 0:
        return None
    tail = compact_text[marker_index + len(marker) :].lstrip(":;=-_")
    if not tail:
        return None
    end_index = len(tail)
    for stop_marker in stop_markers:
        stop_index = tail.find(stop_marker)
        if 0 <= stop_index < end_index:
            end_index = stop_index
    value = tail[:end_index].strip(" .,:;_-")
    if not value:
        return None
    return value[:max_length]


def _template_marker_score(text: str | None) -> int:
    compact = _compact_normalized_text(text)
    return sum(1 for marker in TEMPLATE_MARKERS if marker in compact)


def _is_expected_pdf_template(text: str | None) -> bool:
    return _template_marker_score(text) >= 3


def _project_signature(project_name: str | None) -> str:
    text = _compact_normalized_text(project_name)
    text = re.sub(r"^жк", "", text)
    text = re.sub(r"(\d+)[\-/](\d+)", r"\1к\2", text)
    text = re.sub(r"(\d+)к\.(\d+)", r"\1к\2", text)
    text = re.sub(r"корпус|корп|кор", "к", text)
    return re.sub(r"[^0-9a-zа-я]+", "", text)


def _project_names_match(selected_project_name: str | None, detected_project_name: str | None) -> bool:
    selected_signature = _project_signature(selected_project_name)
    detected_signature = _project_signature(detected_project_name)
    if not selected_signature or not detected_signature:
        return False

    selected_numbers = re.findall(r"\d+", selected_signature)
    detected_numbers = re.findall(r"\d+", detected_signature)
    if selected_numbers and selected_numbers != detected_numbers:
        return False

    if (
        selected_signature == detected_signature
        or selected_signature in detected_signature
        or detected_signature in selected_signature
    ):
        return True

    return SequenceMatcher(None, selected_signature, detected_signature).ratio() >= 0.82


def _extract_project_name(text: str | None) -> str | None:
    compact = _compact_normalized_text(text)
    return _extract_compact_value(compact, "названиежк", PROJECT_STOP_MARKERS)


def _format_project_name(project_name: str | None) -> str:
    value = str(project_name or "").strip(" .,:;_-")
    if not value:
        return ""
    value = re.sub(r"([A-Za-zА-Яа-яЁё])(\d)", r"\1 \2", value)
    value = re.sub(r"(\d)([A-Za-zА-Яа-яЁё])", r"\1 \2", value)
    value = re.sub(r"к\.(\d+)", r"к\1", value, flags=re.IGNORECASE)
    return value


def _extract_text_layer(stream: BinaryIO) -> tuple[str, str | None]:
    try:
        import pypdfium2 as pdfium

        stream.seek(0)
        pdf_bytes = stream.read()
        if not pdf_bytes:
            return "", "Файл PDF пустой."
        document = pdfium.PdfDocument(pdf_bytes)
        chunks: list[str] = []
        for page_index in range(len(document)):
            page = document[page_index]
            text_page = page.get_textpage()
            chunks.append(text_page.get_text_bounded() or "")
        text = _clean_recognized_text("\n".join(chunks))
        if text:
            return text, None
    except ModuleNotFoundError:
        pass
    except Exception:
        pass

    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return "", "На сервере не установлена библиотека pypdf. Установите зависимости из requirements.txt и повторите загрузку."

    try:
        stream.seek(0)
        reader = PdfReader(stream)
        chunks: list[str] = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        return _clean_recognized_text("\n".join(chunks)), None
    except Exception as exc:
        return "", f"Не удалось прочитать PDF: {exc}"


def _get_ocr_engine():
    global _OCR_ENGINE, _OCR_ENGINE_ERROR
    if _OCR_ENGINE is not None or _OCR_ENGINE_ERROR is not None:
        return _OCR_ENGINE, _OCR_ENGINE_ERROR
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ModuleNotFoundError:
        _OCR_ENGINE_ERROR = (
            "Для OCR-распознавания сканов не хватает зависимостей. "
            "Установите rapidocr-onnxruntime и pypdfium2 из requirements.txt."
        )
        return None, _OCR_ENGINE_ERROR
    try:
        _OCR_ENGINE = RapidOCR()
    except Exception as exc:
        _OCR_ENGINE_ERROR = f"Не удалось инициализировать OCR: {exc}"
    return _OCR_ENGINE, _OCR_ENGINE_ERROR


def _extract_text_via_ocr(stream: BinaryIO) -> tuple[str, str | None]:
    engine, engine_error = _get_ocr_engine()
    if engine is None:
        return "", engine_error
    try:
        import pypdfium2 as pdfium
    except ModuleNotFoundError:
        return "", "Для OCR-распознавания сканов не хватает библиотеки pypdfium2."

    try:
        stream.seek(0)
        pdf_bytes = stream.read()
        if not pdf_bytes:
            return "", "Файл PDF пустой."
        document = pdfium.PdfDocument(pdf_bytes)
        page_texts: list[str] = []
        for page_index in range(len(document)):
            page = document[page_index]
            bitmap = page.render(scale=2.5)
            image = bitmap.to_pil()
            image_buffer = BytesIO()
            image.save(image_buffer, format="PNG")
            result, _elapsed = engine(image_buffer.getvalue())
            lines: list[str] = []
            for item in result or []:
                if len(item) >= 2 and str(item[1]).strip():
                    lines.append(str(item[1]).strip())
            if lines:
                page_texts.append("\n".join(lines))
        return _clean_recognized_text("\n\n".join(page_texts)), None
    except Exception as exc:
        return "", f"OCR не смог обработать PDF-скан: {exc}"


def _find_apartment_number(text: str) -> str | None:
    compact = _compact_normalized_text(text)
    compact_value = _extract_compact_value(compact, "номерквартиры", APARTMENT_STOP_MARKERS)
    if compact_value:
        compact_match = COMPACT_APARTMENT_RE.match(compact_value)
        if compact_match:
            return compact_match.group(1).strip(" .,:;_-")

    match = APARTMENT_RE.search(text or "")
    if match:
        return match.group(1).strip()
    fallback = re.search(r"\bкв\.?\s*([0-9]+[A-Za-zА-Яа-яЁё/-]*)\b", text or "", re.IGNORECASE)
    if fallback:
        return fallback.group(1).strip()
    return None


def _find_inspection_date(text: str) -> date | None:
    compact = _compact_normalized_text(text)
    compact_match = COMPACT_DATE_RE.search(compact)
    if compact_match:
        parsed = parse_date(compact_match.group(1))
        if parsed:
            return parsed

    lowered = (text or "").lower()
    for match in DATE_RE.finditer(text or ""):
        left = max(match.start() - 100, 0)
        context = lowered[left : match.end() + 60]
        if "осмотр" in context or "акт" in context or "дата" in context or "прием" in context:
            parsed = parse_date(match.group(0))
            if parsed:
                return parsed
    first = DATE_RE.search(text or "")
    return parse_date(first.group(0)) if first else None


def _map_pdf_point_to_work_point(pdf_point_number: str, section_title: str | None) -> str:
    normalized_title = normalize_text(section_title or "").replace("ё", "е")
    normalized_title = re.sub(r"[^a-zа-я0-9]+", "", normalized_title)
    for marker, work_point in PDF_POINT_TITLE_ALIASES:
        if marker in normalized_title:
            return work_point
    mapped = PDF_POINT_TO_WORK_POINT.get(str(pdf_point_number).strip())
    if mapped:
        return mapped
    if str(pdf_point_number).strip() in VISIBLE_WORK_POINT_NUMBERS:
        return str(pdf_point_number).strip()
    return "22"


def _split_point_heading(description: str) -> tuple[str, str]:
    match = POINT_HEADER_RE.match(description or "")
    if not match:
        return "", (description or "").strip()
    title = (match.group(1) or "").strip(" .")
    body = (match.group(2) or "").strip()
    return title, body


def _clean_point_description(description: str) -> str:
    value = SIGNATURE_TAIL_RE.sub("", description or "").strip()
    value = re.sub(r"^_+\s*", "", value)
    value = re.sub(r"\s*_+\s*$", "", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip(" .")


def _extract_point_remarks(text: str) -> list[PdfRemarkPreview]:
    remarks: list[PdfRemarkPreview] = []
    current_point: str | None = None
    current_lines: list[str] = []
    inside_remarks_block = False

    def flush_current() -> None:
        nonlocal current_point, current_lines
        if not current_point:
            current_lines = []
            return
        description = "\n".join(line.strip() for line in current_lines if line.strip()).strip()
        section_title, section_body = _split_point_heading(description)
        mapped_point = _map_pdf_point_to_work_point(current_point, section_title)
        cleaned_description = _clean_point_description(section_body or description)
        if not cleaned_description and section_title:
            cleaned_description = _clean_point_description(section_title)
        if normalize_text(cleaned_description).replace("ё", "е") == "прочее":
            cleaned_description = ""
        if cleaned_description and not is_no_remark_text(cleaned_description):
            remarks.append(PdfRemarkPreview(point_number=mapped_point, description=cleaned_description, active=True))
        current_point = None
        current_lines = []

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized_line = normalize_text(line).replace("ё", "е")
        if "выявленные недостатки" in normalized_line:
            inside_remarks_block = True
            continue
        if not inside_remarks_block:
            continue
        match = POINT_LINE_RE.match(line)
        if match:
            flush_current()
            current_point = match.group(1)
            tail = (match.group(2) or "").strip()
            if tail:
                current_lines.append(tail)
            continue
        if current_point:
            current_lines.append(line)
    flush_current()
    return remarks


def recognize_pdf_act(stream: BinaryIO, filename: str, project_name: str) -> PdfActPreview:
    text, text_error = _extract_text_layer(stream)
    used_ocr = False
    ocr_error: str | None = None
    ocr_text = ""
    needs_ocr = (
        not text
        or _template_marker_score(text) < 3
        or not _find_apartment_number(text)
        or not _find_inspection_date(text)
    )
    if needs_ocr:
        ocr_text, ocr_error = _extract_text_via_ocr(stream)

    detected_project_name = _extract_project_name(text)
    if not detected_project_name and ocr_text:
        detected_project_name = _extract_project_name(ocr_text)
        used_ocr = bool(detected_project_name)

    apartment_number = _find_apartment_number(text)
    if not apartment_number and ocr_text:
        apartment_number = _find_apartment_number(ocr_text)
        used_ocr = used_ocr or bool(apartment_number)

    inspection_date = _find_inspection_date(text)
    if not inspection_date and ocr_text:
        inspection_date = _find_inspection_date(ocr_text)
        used_ocr = used_ocr or bool(inspection_date)

    layer_remarks = _extract_point_remarks(text)
    ocr_remarks = _extract_point_remarks(ocr_text)
    remarks = layer_remarks
    if len(ocr_remarks) > len(layer_remarks):
        remarks = ocr_remarks
        used_ocr = used_ocr or bool(ocr_remarks)

    template_ok = _is_expected_pdf_template(text) or _is_expected_pdf_template(ocr_text)
    prefix = _project_prefix(project_name)
    project_ok = _project_names_match(project_name, detected_project_name)
    preview = PdfActPreview(
        filename=filename,
        template_ok=template_ok,
        project_ok=project_ok,
        project_prefix=prefix,
        project_name=project_name if project_ok and project_name else _format_project_name(detected_project_name),
        apartment_number=apartment_number,
        inspection_date=inspection_date,
        remarks=remarks,
        used_ocr=used_ocr,
    )

    if not text and not ocr_text:
        if text_error:
            preview.warnings.append(text_error)
        if ocr_error:
            preview.warnings.append(ocr_error)
        if not preview.warnings:
            preview.warnings.append("Не удалось получить текст ни из PDF, ни через OCR.")
        return preview

    if text_error and not text:
        preview.warnings.append(text_error)
    if ocr_error and not ocr_text and needs_ocr:
        preview.warnings.append(ocr_error)

    if used_ocr:
        preview.warnings.append("Текст извлечён через OCR из скана. Обязательно проверьте квартиру, дату и каждый пункт перед сохранением.")

    if not preview.template_ok:
        preview.warnings.append(
            "Файл не похож на PDF-акт нужного шаблона. Загрузите акт, где есть поля «Название ЖК», «Номер квартиры», «ФИО клиента» и блок «Выявленные недостатки»."
        )
        preview.apartment_number = None
        preview.inspection_date = None
        preview.remarks = []
        return preview

    if not preview.project_ok:
        if preview.project_name:
            preview.warnings.append(f"В PDF указан ЖК «{preview.project_name}», а выбран объект «{project_name}».")
        else:
            preview.warnings.append("Не удалось подтвердить ЖК по полю «Название ЖК» внутри PDF.")

    if not preview.apartment_number:
        preview.warnings.append("Не удалось найти номер квартиры в PDF.")
    if not preview.inspection_date:
        preview.warnings.append("Не удалось найти дату осмотра в PDF.")
    if not preview.remarks:
        preview.warnings.append("Замечания по пунктам не найдены или в акте указано, что замечания отсутствуют.")
    return preview
