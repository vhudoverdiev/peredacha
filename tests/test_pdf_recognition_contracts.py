from datetime import date
import builtins
import unittest
from pathlib import Path

from app.services import pdf_recognition as recognition


class PdfRecognitionContractsTests(unittest.TestCase):
    def test_recognition_review_page_allows_manual_rows_and_po_mode(self):
        template = Path("app/templates/task_recognition.html").read_text(encoding="utf-8")

        self.assertIn("data-task-recognition-add-row", template)
        self.assertIn("btn btn-sm btn-success task-recognition-add-row-btn", template)
        self.assertNotIn("btn btn-sm btn-outline-success task-recognition-add-row-btn", template)
        self.assertIn("data-task-recognition-row-template", template)
        self.assertIn("task-recognition-po-toggle", template)
        self.assertIn(".btn-check:checked + .task-recognition-po-toggle", template)
        self.assertIn("-webkit-text-fill-color: #ffffff", template)
        self.assertIn('name="po_mode"', template)
        self.assertIn("ПО", template)

    def test_manual_act_page_has_po_mode_with_explanation(self):
        template = Path("app/templates/task_form.html").read_text(encoding="utf-8")

        self.assertIn('id="manualActPoMode"', template)
        self.assertIn('name="po_mode"', template)
        self.assertIn("task-manual-po-toggle", template)
        self.assertIn("идентичные замечания остаются невыполненными", template)

    def test_no_remark_detection_requires_meaningful_marker(self):
        self.assertTrue(recognition.is_no_remark_text(recognition.NO_REMARK_MARKERS[0]))
        self.assertTrue(recognition.is_no_remark_text(f"  {recognition.NO_REMARK_MARKERS[-1]}  "))
        self.assertFalse(recognition.is_no_remark_text(""))
        self.assertFalse(recognition.is_no_remark_text("broken window handle"))

    def test_clean_recognized_text_normalizes_pdf_noise_and_point_boundaries(self):
        cleaned = recognition._clean_recognized_text("No 12\r\n\n\nfirst part p. 7: window issue")

        self.assertIn("№ 12", cleaned)
        self.assertNotIn("\r", cleaned)
        self.assertNotIn("\n\n\n", cleaned)

    def test_compact_value_extraction_stops_at_next_known_marker(self):
        compact = "prefixmarker:value-123stopnext"

        self.assertEqual(recognition._extract_compact_value(compact, "marker", ("stop",)), "value-123")
        self.assertIsNone(recognition._extract_compact_value(compact, "missing", ("stop",)))

    def test_template_scoring_requires_several_markers_before_accepting_pdf(self):
        text = "\n".join(recognition.TEMPLATE_MARKERS[:2])
        full_text = "\n".join(recognition.TEMPLATE_MARKERS[:3])

        self.assertEqual(recognition._template_marker_score(text), 2)
        self.assertFalse(recognition._is_expected_pdf_template(text))
        self.assertTrue(recognition._is_expected_pdf_template(full_text))

    def test_project_name_matching_tolerates_formatting_but_not_different_numbers(self):
        self.assertTrue(recognition._project_names_match("ЖК 100 квартал корпус 2", "100 квартал к.2"))
        self.assertFalse(recognition._project_names_match("ЖК 100 квартал корпус 2", "100 квартал к.3"))
        self.assertFalse(recognition._project_names_match("", "100 квартал"))

    def test_apartment_number_and_inspection_date_are_extracted_from_compact_fields(self):
        text = f"{recognition.TEMPLATE_MARKERS[1]} 42/1 {recognition.APARTMENT_STOP_MARKERS[0]}\nРґР°С‚Р° 05.07.2026"

        self.assertEqual(recognition._find_apartment_number(text), "42/")
        self.assertEqual(recognition._find_inspection_date(text), date(2026, 7, 5))

    def test_point_heading_mapping_and_cleanup_return_actionable_remark(self):
        title, body = recognition._split_point_heading("РћРєРЅР°: sash does not close")

        self.assertEqual(title, "РћРєРЅР°")
        self.assertEqual(body, "sash does not close")
        self.assertEqual(recognition._map_pdf_point_to_work_point("7", title), "16")
        self.assertEqual(recognition._clean_point_description(" _ sash does not close _ "), "sash does not close")

    def test_extract_point_remarks_ignores_no_remark_rows_and_maps_known_sections(self):
        text = "\n".join([
            "header ignored before remark block",
            "выявленные недостатки",
            "7. Windows: sash does not close",
            f"8. {recognition.NO_REMARK_MARKERS[-1]}",
            "21. custom unmapped point",
        ])

        remarks = recognition._extract_point_remarks(text)

        self.assertEqual([(remark.point_number, remark.description, remark.active) for remark in remarks], [
            ("16", "sash does not close", True),
            ("21", "custom unmapped point", True),
        ])

    def test_ocr_engine_import_system_dependency_error_is_reported_not_raised(self):
        original_import = builtins.__import__
        original_engine = recognition._OCR_ENGINE
        original_error = recognition._OCR_ENGINE_ERROR

        def fake_import(name, *args, **kwargs):
            if name == "rapidocr_onnxruntime":
                raise OSError("libxcb.so.1: cannot open shared object file: No such file or directory")
            return original_import(name, *args, **kwargs)

        try:
            recognition._OCR_ENGINE = None
            recognition._OCR_ENGINE_ERROR = None
            builtins.__import__ = fake_import

            engine, error = recognition._get_ocr_engine()
        finally:
            builtins.__import__ = original_import
            recognition._OCR_ENGINE = original_engine
            recognition._OCR_ENGINE_ERROR = original_error

        self.assertIsNone(engine)
        self.assertIn("OCR-распознавание сканов сейчас недоступно", error)
        self.assertIn("libxcb.so.1", error)


if __name__ == "__main__":
    unittest.main()
