from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "{%s}" % WORD_NS
ET.register_namespace("w", WORD_NS)

AVR_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "document_templates" / "avr_template.docx"


def format_doc_date(value: date | datetime | str | None) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    text = str(value).strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d.%m.%Y")
        except ValueError:
            pass
    return text


def format_input_date(value: date | datetime | str | None) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return ""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return text


def default_avr_phrase(inspection_date: date | datetime | str | None) -> str:
    display_date = format_doc_date(inspection_date) or "__.__.____"
    return f"Все замечания с акта осмотра от {display_date} устранены"


def safe_avr_filename(project_name: str, apartment_number: str, premise_type: str | None = None) -> str:
    premise_prefix = "Komm" if (premise_type or "").strip().lower() == "commercial" else "Kv"
    stem = f"AVR-{project_name} - {premise_prefix}{apartment_number or 'kv'}"
    stem = re.sub(r"[\\/:*?\"<>|]+", " ", stem, flags=re.UNICODE)
    stem = re.sub(r"\s+", " ", stem, flags=re.UNICODE).strip(" .")
    return f"{stem or 'avr'}.docx"


def build_avr_docx(output_path: Path, values: dict[str, str], template_path: Path | None = None) -> None:
    source = template_path or AVR_TEMPLATE_PATH
    if not source.exists():
        raise FileNotFoundError(f"Шаблон АВР не найден: {source}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as src, zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                data = _fill_document_xml(data, values)
            dst.writestr(item, data)


def _fill_document_xml(data: bytes, values: dict[str, str]) -> bytes:
    root = ET.fromstring(data)
    tables = list(root.iter(f"{XML_NS}tbl"))

    if not tables:
        _fill_linear_template(root, values)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    _set_table_cell_text(tables, 0, 0, 1, values.get("apartment_number", ""))
    _set_table_cell_text(tables, 0, 0, 3, values.get("floor", ""))
    _set_table_cell_text(tables, 0, 0, 5, values.get("address", ""))
    _set_table_cell_text(tables, 1, 0, 1, format_avr_person_lines(values.get("developer_representative", "")))
    _set_table_cell_text(tables, 2, 0, 1, format_avr_person_lines(values.get("owner_name", "")))
    _set_table_cell_text(tables, 3, 0, 1, values.get("inspection_date", ""))

    _set_table_cell_text(tables, 3, 0, 3, ":")
    _set_table_cell_text(tables, 3, 1, 0, values.get("completion_phrase", ""), force_plain=True)

    act_date = values.get("act_date", "")
    _set_table_cell_text(tables, 4, 1, 1, _date_with_year_word(act_date))

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _fill_linear_template(root: ET.Element, values: dict[str, str]) -> None:
    paragraphs = [p for p in root.iter(f"{XML_NS}p") if _paragraph_text(p).strip()]
    act_date = _date_with_year_word(values.get("act_date", ""))
    premise_type = (values.get("premise_type") or "apartment").strip().lower()
    premise_number = values.get("apartment_number", "")
    developer = format_avr_person_lines(values.get("developer_representative", ""))
    owner = format_avr_person_lines(values.get("owner_name", ""))
    date_index = _set_first_matching_paragraph_segments(paragraphs, "дата", [(act_date, True)])
    if date_index is None and len(paragraphs) > 1:
        _set_paragraph_segments(paragraphs[1], [(act_date, True)])
    if premise_type == "commercial":
        premise_segments = [
            ("Коммерция № ", False),
            (premise_number, True),
            (", по адресу: ", False),
            (values.get("address", ""), True),
        ]
    else:
        premise_segments = [
            ("Квартира № ", False),
            (premise_number, True),
            (", расположенная на ", False),
            (values.get("floor", ""), True),
            (" этаже, по адресу: ", False),
            (values.get("address", ""), True),
        ]
    _set_first_matching_paragraph_segments(paragraphs, "по адресу", premise_segments)
    _set_first_matching_paragraph_segments(
        paragraphs,
        "В присутствии",
        [
            ("В присутствии представителя Застройщика: ", False),
            (developer, True),
            (" и ", False),
            (owner, True),
        ],
    )

    claim_text = "В соответствии с претензией выполнено следующее:"
    claim_index = _set_first_matching_paragraph(paragraphs, "В соответствии с претензией", claim_text)

    if claim_index is not None:
        completion_lines = [line.strip() for line in str(values.get("completion_phrase") or "").splitlines() if line.strip()]
        if not completion_lines:
            completion_lines = [default_avr_phrase(None)]
        for offset, line in enumerate(completion_lines, start=1):
            target_index = claim_index + offset
            if target_index >= len(paragraphs):
                break
            if offset == 1 or _is_underline_paragraph(paragraphs[target_index]):
                _set_paragraph_segments(
                    paragraphs[target_index],
                    [("___", False), (line, True), ("___________________________________________________", False)],
                    force_plain=True,
                )


def _date_with_year_word(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.lower().endswith("года") else f"{text} года"


def format_avr_person_lines(value: str | None) -> str:
    lines = [line.strip() for line in re.split(r"[\r\n;]+", str(value or "")) if line.strip()]
    return "\n".join(format_avr_person_name(line) for line in lines)


def format_avr_person_name(value: str | None) -> str:
    text = re.sub(r"\([^)]*\)", "", str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    parts = text.split(" ")
    surname = parts[0]
    initials = _person_initials(parts[1:])
    gender = _person_gender(surname, parts[1:])
    declined = _decline_surname_genitive(surname, gender)
    return f"{declined} {initials}".strip()


def _person_initials(parts: list[str]) -> str:
    result = []
    for part in parts:
        token = part.strip(" .")
        if not token:
            continue
        if "." in part and re.fullmatch(r"(?:[A-Za-zА-Яа-яЁё]\.?)+", part.strip()):
            letters = re.findall(r"[A-Za-zА-Яа-яЁё]", part)
            result.extend(f"{letter.upper()}." for letter in letters)
        else:
            result.append(f"{token[0].upper()}.")
    return "".join(result)


def _person_gender(surname: str, name_parts: list[str]) -> str:
    lowered_parts = [part.lower().strip(" .") for part in name_parts]
    if any(part.endswith(("вна", "чна", "кызы")) for part in lowered_parts):
        return "female"
    if any(part.endswith(("вич", "ич", "оглы")) for part in lowered_parts):
        return "male"
    return "female" if surname.lower().endswith(("а", "я")) else "male"


def _decline_surname_genitive(surname: str, gender: str) -> str:
    if "-" in surname:
        first, last = surname.rsplit("-", 1)
        return f"{first}-{_decline_surname_genitive(last, gender)}"

    lower = surname.lower()
    if gender == "female":
        if lower.endswith(("ова", "ева", "ёва", "ина", "ына")):
            return surname[:-1] + "ой"
        if lower.endswith("ая"):
            return surname[:-2] + "ой"
        if lower.endswith("яя"):
            return surname[:-2] + "ей"
        if lower.endswith("а"):
            return surname[:-1] + "ой"
        if lower.endswith("я"):
            return surname[:-1] + "и"
        return surname

    if lower.endswith(("ий", "ый", "ой")):
        return surname[:-2] + "ого"
    if lower.endswith(("а", "я", "о", "е", "и", "ы", "у", "ю")):
        return surname
    return surname + "а"


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(text.text or "" for text in paragraph.iter(f"{XML_NS}t"))


def _set_first_matching_paragraph(paragraphs: list[ET.Element], marker: str, text: str) -> int | None:
    marker_normalized = marker.lower()
    for index, paragraph in enumerate(paragraphs):
        if marker_normalized in _paragraph_text(paragraph).lower():
            _set_paragraph_text(paragraph, text)
            return index
    return None


def _set_first_matching_paragraph_segments(paragraphs: list[ET.Element], marker: str, segments: list[tuple[str, bool]]) -> int | None:
    marker_normalized = marker.lower()
    for index, paragraph in enumerate(paragraphs):
        if marker_normalized in _paragraph_text(paragraph).lower():
            _set_paragraph_segments(paragraph, segments)
            return index
    return None


def _is_underline_paragraph(paragraph: ET.Element) -> bool:
    text = _paragraph_text(paragraph).strip()
    return bool(text) and set(text) <= {"_"}


def _set_table_cell_text(tables: list[ET.Element], table_index: int, row_index: int, cell_index: int, text: str, force_plain: bool = False) -> None:
    try:
        cell = tables[table_index].findall(f"{XML_NS}tr")[row_index].findall(f"{XML_NS}tc")[cell_index]
    except IndexError:
        return
    paragraph = cell.find(f"{XML_NS}p")
    if paragraph is None:
        paragraph = ET.SubElement(cell, f"{XML_NS}p")
    _set_paragraph_text(paragraph, text, force_plain=force_plain)


def _set_paragraph_text(paragraph: ET.Element, text: str, force_plain: bool = False) -> None:
    _set_paragraph_segments(paragraph, [(text, False)], force_plain=force_plain)


def _set_paragraph_segments(paragraph: ET.Element, segments: list[tuple[str, bool]], force_plain: bool = False) -> None:
    ppr = paragraph.find(f"{XML_NS}pPr")
    run_props = None
    first_run = paragraph.find(f"{XML_NS}r")
    if first_run is not None:
        rpr = first_run.find(f"{XML_NS}rPr")
        if rpr is not None:
            run_props = _deepcopy(rpr)
            if force_plain:
                _remove_bold(run_props)
                _remove_underline(run_props)

    for child in list(paragraph):
        paragraph.remove(child)
    if ppr is not None:
        paragraph.append(_deepcopy(ppr))

    for text, underline in segments:
        run = ET.SubElement(paragraph, f"{XML_NS}r")
        if run_props is not None or underline:
            rpr = _deepcopy(run_props) if run_props is not None else ET.Element(f"{XML_NS}rPr")
            if force_plain:
                _remove_bold(rpr)
                _remove_underline(rpr)
            if underline and rpr.find(f"{XML_NS}u") is None:
                u = ET.SubElement(rpr, f"{XML_NS}u")
                u.set(f"{XML_NS}val", "single")
            if force_plain and not underline:
                _remove_underline(rpr)
            run.append(rpr)
        parts = str(text or "").split("\n")
        for index, part in enumerate(parts):
            if index:
                ET.SubElement(run, f"{XML_NS}br")
            text_node = ET.SubElement(run, f"{XML_NS}t")
            if part.startswith(" ") or part.endswith(" "):
                text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            text_node.text = part


def _deepcopy(element: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(element, encoding="utf-8"))


def _remove_bold(run_props: ET.Element) -> None:
    for tag in ("b", "bCs"):
        for child in list(run_props.findall(f"{XML_NS}{tag}")):
            run_props.remove(child)


def _remove_underline(run_props: ET.Element) -> None:
    for child in list(run_props.findall(f"{XML_NS}u")):
        run_props.remove(child)


def _remove_underline(run_props: ET.Element) -> None:
    for child in list(run_props.findall(f"{XML_NS}u")):
        run_props.remove(child)
