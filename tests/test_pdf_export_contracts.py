from datetime import date
import unittest

from app.models import Apartment, Project, STATUS_CONTRACTOR, Task, WorkPoint
from app.services.pdf_export import (
    _date,
    _latin_text,
    _limit_pdf_text,
    _pdf_escape,
    _pdf_text_hex,
    _point,
    _premise,
    _safe_filename_part,
    _status,
    _task_text,
    _wrap_for_width,
)


class PdfExportContractsTests(unittest.TestCase):
    def test_safe_filename_part_removes_filesystem_metacharacters_and_has_fallback(self):
        self.assertEqual(_safe_filename_part('  Report: A/B*C? "Q" <1>|  '), "Report A B C Q 1")
        self.assertEqual(_safe_filename_part("  "), "export")
        self.assertEqual(_safe_filename_part(None), "export")

    def test_text_limiting_is_deterministic_and_preserves_meaningful_newlines(self):
        text = "Line 1\n\n\nLine 2 " + "x" * 20

        limited = _limit_pdf_text(text, max_chars=14)

        self.assertEqual(limited, "Line 1\n\nLine 2…")
        self.assertEqual(_limit_pdf_text("short", max_chars=20), "short")

    def test_pdf_string_helpers_escape_special_chars_and_encode_unicode_text(self):
        self.assertEqual(_pdf_escape(r"A\(B)"), r"A\\\(B\)")
        self.assertEqual(_pdf_text_hex("AB"), "<00410042>")
        self.assertEqual(_pdf_text_hex(""), "<>")

    def test_wrap_for_width_splits_long_words_and_caps_row_height(self):
        wrapped = _wrap_for_width("short supercalifragilisticexpialidocious tail", width=48, font_size=10)

        self.assertGreater(len(wrapped), 1)
        self.assertTrue(all(len(line) <= 10 for line in wrapped[1:-1]))
        self.assertLessEqual(len(_wrap_for_width("\n".join(str(i) for i in range(20)), width=48, font_size=10)), 7)

    def test_task_row_fields_use_public_model_contracts_and_safe_fallbacks(self):
        project = Project(name="Project")
        apartment = Apartment(project=project, apartment_number="12")
        point = WorkPoint(point_number="3", short_name="Windows")
        task = Task(
            source_uid="pdf-export-task",
            project=project,
            apartment=apartment,
            work_point=point,
            description="",
            source_cell_value="Source remark",
            status=STATUS_CONTRACTOR,
        )

        self.assertEqual(_task_text(task), "Source remark")
        self.assertEqual(_premise(task), apartment.label())
        self.assertEqual(_point(task), f"3. {point.display_name}")
        self.assertTrue(_status(task))
        self.assertEqual(_date(date(2026, 7, 5)), "05.07.2026")

    def test_latin_text_strips_control_characters_without_dropping_plain_content(self):
        self.assertEqual(_latin_text("Alpha\tBeta\x01Gamma", max_chars=100), "Alpha Beta Gamma")


if __name__ == "__main__":
    unittest.main()
