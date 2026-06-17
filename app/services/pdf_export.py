from __future__ import annotations

from datetime import datetime
from pathlib import Path
import math
import re
import unicodedata
from typing import Iterable, Sequence

from flask import current_app

from app.models import Task


MM_TO_PT = 72 / 25.4
A4_LANDSCAPE = (841.89, 595.28)


def _safe_filename_part(value: str | None) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", " ", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text or "export"


def _task_text(task: Task) -> str:
    return str(task.description or task.source_cell_value or "").strip()


def _premise(task: Task) -> str:
    return task.apartment.label() if task.apartment else "-"


def _point(task: Task) -> str:
    if not task.work_point:
        return "-"
    number = str(task.work_point.point_number or "").strip()
    name = str(task.work_point.display_name or "").strip()
    return f"{number}. {name}" if number and name else (number or name or "-")


def _status(task: Task) -> str:
    try:
        return task.status_label()
    except Exception:
        return str(getattr(task, "status", "") or "")


def _date(value) -> str:
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _limit_pdf_text(value: object, max_chars: int = 520) -> str:
    """Keep PDF table rows from becoming taller than a page."""
    text = str(value if value is not None else "").replace("\r", " ").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _register_fonts() -> tuple[str, str]:
    """Register Cyrillic-friendly fonts for ReportLab when ReportLab is installed."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular = _find_ttf_font(False)
    bold = _find_ttf_font(True)
    if regular:
        pdfmetrics.registerFont(TTFont("CRMDejaVu", regular))
        if bold:
            pdfmetrics.registerFont(TTFont("CRMDejaVuBold", bold))
            return "CRMDejaVu", "CRMDejaVuBold"
        return "CRMDejaVu", "CRMDejaVu"
    return "Helvetica", "Helvetica-Bold"


def _as_paragraph(value: object, style, max_chars: int = 520):
    from xml.sax.saxutils import escape
    from reportlab.platypus import Paragraph

    text = escape(_limit_pdf_text(value, max_chars=max_chars))
    return Paragraph(text.replace("\n", "<br/>"), style)


def _export_table_pdf_reportlab(
    *,
    title: str,
    filename_prefix: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    column_widths: Sequence[int] | None = None,
) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, LongTable, TableStyle

    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_filename_part(filename_prefix)}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.pdf"

    font_regular, font_bold = _register_fonts()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CrmPdfTitle",
        parent=styles["Title"],
        fontName=font_bold,
        fontSize=14,
        leading=18,
        alignment=TA_LEFT,
        spaceAfter=8,
        textColor=colors.black,
    )
    header_style = ParagraphStyle(
        "CrmPdfHeader",
        fontName=font_bold,
        fontSize=8.5,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.black,
    )
    cell_style = ParagraphStyle(
        "CrmPdfCell",
        fontName=font_regular,
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        textColor=colors.black,
    )

    pdf = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    data = [[_as_paragraph(header, header_style) for header in headers]]
    if rows:
        data.extend([[_as_paragraph(cell, cell_style) for cell in row] for row in rows])
    else:
        data.append([_as_paragraph("Нет данных", cell_style)] + [_as_paragraph("", cell_style) for _ in headers[1:]])

    if not column_widths:
        usable_width = landscape(A4)[0] - 20 * mm
        column_widths = [usable_width / max(len(headers), 1)] * max(len(headers), 1)
    else:
        column_widths = [w * mm for w in column_widths]

    table = LongTable(data, colWidths=column_widths, repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F7")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
    ]))

    pdf.build([_as_paragraph(title, title_style), Spacer(1, 4), table])
    return path


TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E", "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y",
    "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U", "Ф": "F",
    "Х": "H", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Sch", "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    "№": "N", "—": "-", "–": "-", "…": "...", "×": "x", "«": '"', "»": '"', "₽": "rub.",
}


def _latin_text(value: object, max_chars: int = 520) -> str:
    text = _limit_pdf_text(value, max_chars=max_chars)
    text = "".join(TRANSLIT.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("\t", " ")
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", text)
    return text


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_text_hex(text: str) -> str:
    """Return UTF-16BE hex string for a Type0 Identity-H PDF font.

    This keeps Cyrillic readable in the dependency-free fallback PDF instead
    of transliterating Russian text to Latin.
    """
    return "<" + str(text or "").encode("utf-16-be").hex().upper() + ">"


def _wrap_for_width(text: str, width: float, font_size: float) -> list[str]:
    # Approximate Helvetica average char width. Good enough for fallback mode.
    max_chars = max(8, int(width / (font_size * 0.48)))
    lines: list[str] = []
    for raw_line in str(text).splitlines() or [""]:
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            if len(word) > max_chars:
                if current:
                    lines.append(current)
                    current = ""
                for i in range(0, len(word), max_chars):
                    lines.append(word[i:i + max_chars])
                continue
            candidate = word if not current else f"{current} {word}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines[:7] if len(lines) > 7 else lines


def _build_simple_pdf(path: Path, page_streams: list[str]) -> None:
    """Build a small dependency-free PDF with Unicode Cyrillic text.

    The fallback uses Type0 Identity-H fonts and the viewer's Arial/Arial-Bold
    substitute. It is not as pretty as ReportLab, but it keeps Russian text
    readable and black when ReportLab is not installed on the server.
    """
    objects: list[bytes] = []
    page_count = len(page_streams)
    font1_descriptor_id = 3 + page_count * 2
    font1_id = font1_descriptor_id + 1
    font1_cid_id = font1_descriptor_id + 2
    font2_descriptor_id = font1_descriptor_id + 3
    font2_id = font1_descriptor_id + 4
    font2_cid_id = font1_descriptor_id + 5

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_ids = [3 + i * 2 for i in range(page_count)]
    kids = " ".join(f"{obj_id} 0 R" for obj_id in page_ids)
    objects.append(f"<< /Type /Pages /Count {page_count} /Kids [{kids}] >>".encode("latin-1"))

    for index, stream in enumerate(page_streams):
        page_obj_id = page_ids[index]
        content_obj_id = page_obj_id + 1
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {A4_LANDSCAPE[0]:.2f} {A4_LANDSCAPE[1]:.2f}] "
            f"/Resources << /Font << /F1 {font1_id} 0 R /F2 {font2_id} 0 R >> >> "
            f"/Contents {content_obj_id} 0 R >>"
        )
        objects.append(page.encode("latin-1"))
        stream_bytes = stream.encode("latin-1", errors="replace")
        content = b"<< /Length " + str(len(stream_bytes)).encode("latin-1") + b" >>\nstream\n" + stream_bytes + b"\nendstream"
        objects.append(content)

    objects.append(
        b"<< /Type /FontDescriptor /FontName /ArialMT /Flags 4 /Ascent 905 /Descent -212 "
        b"/CapHeight 716 /ItalicAngle 0 /StemV 80 /FontBBox [-665 -325 2000 1040] >>"
    )
    objects.append(
        f"<< /Type /Font /Subtype /Type0 /BaseFont /ArialMT /Encoding /Identity-H "
        f"/DescendantFonts [{font1_cid_id} 0 R] >>".encode("latin-1")
    )
    objects.append(
        f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /ArialMT "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        f"/FontDescriptor {font1_descriptor_id} 0 R /DW 500 >>".encode("latin-1")
    )
    objects.append(
        b"<< /Type /FontDescriptor /FontName /Arial-BoldMT /Flags 4 /Ascent 905 /Descent -212 "
        b"/CapHeight 716 /ItalicAngle 0 /StemV 100 /FontBBox [-665 -325 2000 1040] >>"
    )
    objects.append(
        f"<< /Type /Font /Subtype /Type0 /BaseFont /Arial-BoldMT /Encoding /Identity-H "
        f"/DescendantFonts [{font2_cid_id} 0 R] >>".encode("latin-1")
    )
    objects.append(
        f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Arial-BoldMT "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        f"/FontDescriptor {font2_descriptor_id} 0 R /DW 500 >>".encode("latin-1")
    )

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_num, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_num} 0 obj\n".encode("latin-1"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)+1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1")
    )
    path.write_bytes(bytes(pdf))


def _font_candidates(bold: bool = False) -> list[str]:
    if bold:
        return [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/local/share/fonts/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
        ]
    return [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/local/share/fonts/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]


def _find_ttf_font(bold: bool = False) -> str | None:
    for candidate in _font_candidates(bold=bold):
        if Path(candidate).exists():
            return candidate
    return None


def _export_table_pdf_pillow(
    *,
    title: str,
    filename_prefix: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    column_widths: Sequence[int] | None = None,
) -> Path:
    """Image-based fallback PDF with readable Cyrillic.

    This is used only when ReportLab is not installed on the user's machine.
    It renders text to page images through Pillow and then saves those images as
    a PDF. The result is not selectable text, but it is stable in Edge/Chrome and
    keeps Russian text black and readable.
    """
    from PIL import Image, ImageDraw, ImageFont

    regular_font_path = _find_ttf_font(False)
    bold_font_path = _find_ttf_font(True) or regular_font_path
    if not regular_font_path:
        raise RuntimeError(
            "Для PDF с русским текстом нужен пакет reportlab или системный шрифт Arial/Segoe UI/DejaVu. "
            "Выполните: pip install -r requirements.txt"
        )

    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_filename_part(filename_prefix)}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.pdf"

    # A4 landscape at 150 DPI. This is sharp enough and does not create huge files.
    dpi = 150
    page_w = int(11.69 * dpi)
    page_h = int(8.27 * dpi)
    margin = int(0.32 * dpi)
    usable_w = page_w - margin * 2
    usable_h = page_h - margin * 2

    title_font = ImageFont.truetype(bold_font_path, 28)
    header_font = ImageFont.truetype(bold_font_path, 17)
    cell_font = ImageFont.truetype(regular_font_path, 16)
    small_font = ImageFont.truetype(regular_font_path, 14)

    if not column_widths:
        widths = [usable_w / max(len(headers), 1)] * max(len(headers), 1)
    else:
        total = sum(column_widths) or 1
        widths = [(w / total) * usable_w for w in column_widths]
    widths = [int(w) for w in widths]
    if widths:
        widths[-1] += usable_w - sum(widths)

    table_rows = [list(headers)] + (list(list(r) for r in rows) if rows else [["Нет данных"] + [""] * (len(headers) - 1)])

    def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
        try:
            return draw.textlength(text, font=font)
        except Exception:
            bbox = draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0]

    def wrap_text(draw: ImageDraw.ImageDraw, value: object, font, max_width: int, max_lines: int) -> list[str]:
        text = _limit_pdf_text(value, max_chars=420).replace("\r", " ")
        result: list[str] = []
        for raw_line in str(text).splitlines() or [""]:
            words = raw_line.split()
            if not words:
                result.append("")
                continue
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if text_width(draw, candidate, font) <= max_width:
                    current = candidate
                    continue
                if current:
                    result.append(current)
                    current = ""
                # Break very long words/strings.
                chunk = ""
                for ch in word:
                    if text_width(draw, chunk + ch, font) <= max_width:
                        chunk += ch
                    else:
                        if chunk:
                            result.append(chunk)
                        chunk = ch
                current = chunk
            if current:
                result.append(current)
        if len(result) > max_lines:
            result = result[:max_lines]
            if result:
                result[-1] = result[-1].rstrip(" .,") + "…"
        return result or [""]

    def make_page() -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
        image = Image.new("RGB", (page_w, page_h), "white")
        draw = ImageDraw.Draw(image)
        draw.text((margin, margin), _limit_pdf_text(title, 130), font=title_font, fill=(0, 0, 0))
        return image, draw, margin + 46

    pages: list[Image.Image] = []
    img, draw, y = make_page()

    def draw_row(row: Sequence[object], y_pos: int, is_header: bool = False) -> int:
        font = header_font if is_header else cell_font
        line_h = 22 if is_header else 21
        max_lines = 2 if is_header else 6
        wrapped = [wrap_text(draw, cell, font, max(width - 14, 35), max_lines) for cell, width in zip(row, widths)]
        row_h = max(36 if is_header else 42, 16 + line_h * max((len(lines) for lines in wrapped), default=1))
        row_h = min(row_h, 152)
        if is_header:
            draw.rectangle((margin, y_pos, margin + usable_w, y_pos + row_h), fill=(234, 240, 247))
        else:
            draw.rectangle((margin, y_pos, margin + usable_w, y_pos + row_h), fill=(255, 255, 255))
        x = margin
        for width, lines in zip(widths, wrapped):
            draw.rectangle((x, y_pos, x + width, y_pos + row_h), outline=(203, 213, 225), width=1)
            text_y = y_pos + 8
            for line in lines:
                draw.text((x + 7, text_y), line, font=font, fill=(0, 0, 0))
                text_y += line_h
            x += width
        return y_pos + row_h

    def ensure_space(required: int, with_header: bool = True) -> None:
        nonlocal img, draw, y, pages
        if y + required <= page_h - margin:
            return
        pages.append(img)
        img, draw, y = make_page()
        if with_header and table_rows:
            y = draw_row(table_rows[0], y, is_header=True)

    # First header.
    y = draw_row(table_rows[0], y, is_header=True)
    for raw_row in table_rows[1:]:
        row = list(raw_row)[:len(headers)] + [""] * max(0, len(headers) - len(raw_row))
        # Estimate before drawing on a copy: safe upper bound for most rows.
        ensure_space(150)
        y = draw_row(row, y, is_header=False)
    pages.append(img)

    # Pillow expects RGB images. resolution keeps printed dimensions reasonable.
    first, rest = pages[0], pages[1:]
    first.save(path, "PDF", resolution=float(dpi), save_all=True, append_images=rest)
    return path

def _export_table_pdf_basic(
    *,
    title: str,
    filename_prefix: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    column_widths: Sequence[int] | None = None,
) -> Path:
    """Dependency-free PDF fallback.

    It prevents a 500 error when the server was updated without installing the new
    ReportLab dependency. The main path still uses ReportLab. The fallback keeps
    Cyrillic readable through a Unicode Type0 PDF font and always uses black text.
    """
    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_filename_part(filename_prefix)}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.pdf"

    margin = 28.0
    page_width, page_height = A4_LANDSCAPE
    usable_width = page_width - margin * 2
    if not column_widths:
        widths = [usable_width / max(len(headers), 1)] * max(len(headers), 1)
    else:
        total_mm = sum(column_widths) or 1
        widths = [(w / total_mm) * usable_width for w in column_widths]

    table_rows = [list(headers)] + (list(list(r) for r in rows) if rows else [["Нет данных"] + [""] * (len(headers) - 1)])
    page_streams: list[str] = []
    stream_lines: list[str] = []
    y = page_height - margin

    def new_page() -> None:
        nonlocal stream_lines, y
        if stream_lines:
            page_streams.append("\n".join(stream_lines))
        stream_lines = ["0 0 0 rg 0 0 0 RG"]
        y = page_height - margin
        title_text = _pdf_text_hex(_limit_pdf_text(title, max_chars=120))
        stream_lines.append(f"BT /F2 14 Tf 1 0 0 1 {margin:.2f} {y:.2f} Tm {title_text} Tj ET")
        y -= 24

    def draw_row(row: Sequence[object], is_header: bool = False) -> None:
        nonlocal y
        font_size = 8 if not is_header else 8.5
        line_height = font_size + 2.5
        prepared: list[list[str]] = []
        for cell, width in zip(row, widths):
            prepared.append(_wrap_for_width(_limit_pdf_text(cell), max(width - 8, 20), font_size))
        row_height = max(22, min(94, 8 + line_height * max((len(lines) for lines in prepared), default=1)))
        if y - row_height < margin:
            new_page()
        x = margin
        if is_header:
            stream_lines.append(f"0.90 0.94 0.98 rg {x:.2f} {y - row_height:.2f} {usable_width:.2f} {row_height:.2f} re f")
        else:
            stream_lines.append("1 1 1 rg")
        stream_lines.append("0.80 0.84 0.89 RG 0.35 w")
        for width, lines in zip(widths, prepared):
            stream_lines.append(f"{x:.2f} {y - row_height:.2f} {width:.2f} {row_height:.2f} re S")
            text_y = y - font_size - 6
            font = "F2" if is_header else "F1"
            for line in lines[:7]:
                text_hex = _pdf_text_hex(line)
                stream_lines.append(f"BT /{font} {font_size:.1f} Tf 0 0 0 rg 1 0 0 1 {x + 4:.2f} {text_y:.2f} Tm {text_hex} Tj ET")
                text_y -= line_height
            x += width
        y -= row_height

    new_page()
    draw_row(table_rows[0], is_header=True)
    for row in table_rows[1:]:
        normalized = list(row)[:len(headers)] + [""] * max(0, len(headers) - len(row))
        draw_row(normalized, is_header=False)
    if stream_lines:
        page_streams.append("\n".join(stream_lines))
    _build_simple_pdf(path, page_streams)
    return path


def export_table_pdf(
    *,
    title: str,
    filename_prefix: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    column_widths: Sequence[int] | None = None,
) -> Path:
    try:
        return _export_table_pdf_reportlab(
            title=title,
            filename_prefix=filename_prefix,
            headers=headers,
            rows=rows,
            column_widths=column_widths,
        )
    except ModuleNotFoundError as exc:
        # The app must not crash if the project files were updated but the user
        # did not run `pip install -r requirements.txt`. First use a Pillow
        # image-based fallback because it keeps Russian text readable in Edge.
        if exc.name and exc.name.startswith("reportlab"):
            try:
                return _export_table_pdf_pillow(
                    title=title,
                    filename_prefix=filename_prefix,
                    headers=headers,
                    rows=rows,
                    column_widths=column_widths,
                )
            except ModuleNotFoundError as pillow_exc:
                if pillow_exc.name and pillow_exc.name.startswith("PIL"):
                    raise RuntimeError(
                        "Для PDF с русским текстом установите зависимости: pip install -r requirements.txt"
                    ) from pillow_exc
                raise
        raise


def export_tasks_pdf(tasks: Iterable[Task], filename_prefix: str, title: str = "Замечания") -> Path:
    rows = []
    for task in tasks:
        rows.append([
            _premise(task),
            _point(task),
            _task_text(task),
            _status(task),
            _date(task.completed_date),
        ])
    return export_table_pdf(
        title=title,
        filename_prefix=filename_prefix,
        headers=["№", "Пункт", "Замечание", "Статус", "Дата выполнения"],
        rows=rows,
        column_widths=[18, 42, 145, 28, 28],
    )


def export_assignment_worker_pdf(tasks: Iterable[Task], filename_prefix: str, title: str) -> Path:
    rows = []
    for task in tasks:
        rows.append([
            _premise(task),
            _point(task),
            _task_text(task),
            _status(task),
            _date(task.planned_date),
            _date(task.completed_date),
        ])
    return export_table_pdf(
        title=title,
        filename_prefix=filename_prefix,
        headers=["№", "Пункт", "Задача", "Статус", "План", "Выполнено"],
        rows=rows,
        column_widths=[16, 38, 130, 28, 23, 26],
    )
