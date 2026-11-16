from datetime import date
from io import BytesIO
import builtins
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import pdf_recognition as recognition


class PdfRecognitionContractsTests(unittest.TestCase):
    def test_arch_expert_scanned_schedule_excludes_norms_and_preserves_rooms(self):
        text = """ООО «АрхОблЭкспертиза»
АКТ ОСМОТРА № 139/26-СЭ от 08 сентября 2026 г.
Адрес объекта: г. Архангельск, ул. Нагорная, д. 1, корп. 1, wo 5
Собственник: Иванов
[ARCH_RESULTS]
Жилая комната площадью 10,0 кв.м.:
- на стене слева от окна трещины в штукатурке

Жилая комната площадью 10,0 кв.м.:

- на стене справа трещины
[/ARCH_RESULTS]
СП 71.13330 Требования к штукатурке
[ARCH_RESULTS]
Во всех помещениях у радиаторов отопления стяжка крошится

Устройство оконных отливов без прокладок
[/ARCH_RESULTS]
[ARCH_RESULTS]
Кратность воздухообмена в санузле не соответствует нормативной
[/ARCH_RESULTS]
[ARCH_RESULTS]
Гнезда подрозетников устроены некорректно
[/ARCH_RESULTS]
"""
        with patch.object(recognition, "_extract_text_layer", return_value=("", None)), patch.object(
            recognition, "_extract_text_via_ocr", return_value=(text, None)
        ):
            preview = recognition.recognize_pdf_act(BytesIO(), "225.pdf", "ЖК Роса")
        self.assertTrue(preview.template_ok)
        self.assertTrue(preview.used_ocr)
        self.assertFalse(preview.project_ok)
        self.assertIsNone(preview.apartment_number)
        self.assertEqual(preview.inspection_date, date(2026, 9, 8))
        self.assertEqual([r.point_number for r in preview.remarks], ["11", "11", "13", "17", "10", "24"])
        self.assertTrue(all("СП 71" not in r.description for r in preview.remarks))
        self.assertIn("Жилая комната", preview.remarks[0].description)

    def test_arch_expert_requires_organization_and_results_markers(self):
        self.assertFalse(recognition._is_arch_expert_act("АКТ ОСМОТРА"))
        self.assertEqual(recognition._arch_expert_remarks("Фото 1. Трещина. СП 71"), [])
        self.assertTrue(recognition._is_arch_expert_act("Архангельский Областной\nЦентр Экспертизы"))

    def test_arch_expert_does_not_read_non_table_pages(self):
        from PIL import Image
        with patch.object(recognition, "_ocr_image", return_value="План помещения") as ocr:
            self.assertEqual(recognition._arch_expert_table_text(Image.new("RGB", (600, 800)), "tesseract"), "")
        self.assertEqual(ocr.call_count, 1)

    def test_step_defect_schedule_uses_section_titles_and_ignores_reference_documents(self):
        text = """
АКТ ОСМОТРА
КАЧЕСТВА ЖИЛОГО ПОМЕЩЕНИЯ
1 этап, квартира 492 (11 этаж)
Содержание:
2. Дефектная ведомость 3
1. ИСХОДНЫЕ ДАННЫЕ.
В рамках договора от 05.06.2026 составили настоящий акт о том, что «8» июня 2026 г.
в жилом комплексе «Роса» произведен осмотр.
2. ДЕФЕКТНАЯ ВЕДОМОСТЬ
Полы:
1. Гидроизоляция в туалетной комнате отсутствует. Нарушены требования п. 7.2 СП 29.13330.2011
«Полы». Санузел относится к мокрым помещениям.
2. Требуется удалить наплывы строительных смесей на стяжке. Повсеместно
Потолки:
3 Сколы с оголением рабочей арматуры. Нарушение требований ГОСТ (номер 1,2 на схеме)
Стены:
4 ( Требуется ремонт штукатурки (трещины). (номер 3-9 на схеме)
ОО ee ПО ПО ПО ПО
Оконные блоки:
5 Требуется регулировка ручки окна. (номер 13 на схеме)
Лоджия:
6 Повреждение тонировки витражного остекления.
3. ИСПОЛЬЗУЕМЫЙ ССЫЛОЧНЫЕ ДОКУМЕНТЫ.
1. СП 29.13330.2011 «Полы».
"""
        with patch.object(recognition, "_extract_text_layer", return_value=("", None)), patch.object(
            recognition, "_extract_text_via_ocr", return_value=(text, None)
        ):
            preview = recognition.recognize_pdf_act(BytesIO(b"scan"), "492.pdf", "ЖК Роса")
        self.assertTrue(preview.template_ok)
        self.assertTrue(preview.project_ok)
        self.assertTrue(preview.used_ocr)
        self.assertEqual(preview.apartment_number, "492")
        self.assertEqual(preview.inspection_date, date(2026, 6, 8))
        self.assertEqual([row.point_number for row in preview.remarks], ["13", "13", "11", "11", "17", "20"])
        self.assertEqual(len(preview.remarks), 6)
        self.assertEqual(preview.remarks[0].description.rstrip("."), "Гидроизоляция в туалетной комнате отсутствует")
        self.assertNotIn("схеме", preview.remarks[3].description)

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
        self.assertEqual(recognition._map_pdf_point_to_work_point("7", title), "17")
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
            ("17", "sash does not close", True),
            ("21", "custom unmapped point", True),
        ])

    def test_technical_act_extracts_remarks_before_photos_and_standards(self):
        text = """
АКТ ТЕХНИЧЕСКОГО ОСМОТРА
№ 496-09/11/2026
КВАРТИРЫ № 496,
В ЖИЛОМ КОМПЛЕКСЕ «ЛИСТВА2»,
Северодвинск, 09.11.2026
СОДЕРЖАНИЕ:
3. Перечень выявленных нарушений строительных норм и правил 5-7
В РЕЗУЛЬТАТЕ ОСМОТРА ВЫЯВЛЕНЫ СЛЕДУЮЩИЕ НАРУШЕНИЯ
СТРОИТЕЛЬНЫХ НОРМ И ПРАВИЛ:
1. Стены:
1.1. Следы влаги в коридоре (Фото 1–2)
Нормативное обоснование: СП 50.13330.2024
2. Разбивочные оси:
2.1. Смещение перегородки от разбивочной оси
между спальней и кухней на 30 мм. (Фото 3,
4)
3. Полы:
Замечаний не выявлено.
8. Окна:
8.1. Требуется очистка и регулировка изделий ПВХ
Нормативное обоснование: ГОСТ 30674-2023
10. Горячее и холодное водоснабжение:
10.1. Не закреплён хомут на стояке.
ФОТОТАБЛИЦА К АКТУ ТЕХНИЧЕСКОГО ОСМОТРА:
Фото 1 — п. 1.1. Следы влаги в коридоре
8.2. Повтор в фототаблице
"""
        with patch.object(recognition, "_extract_text_layer", return_value=(text, None)), patch.object(
            recognition, "_extract_text_via_ocr"
        ) as ocr:
            preview = recognition.recognize_pdf_act(BytesIO(), "sample.pdf", "ЖК Листва 2 этап")
            wrong_project = recognition.recognize_pdf_act(BytesIO(), "sample.pdf", "ЖК Листва 1 этап")
            ocr.assert_not_called()

        self.assertTrue(preview.template_ok)
        self.assertTrue(preview.project_ok)
        self.assertFalse(wrong_project.project_ok)
        self.assertEqual(preview.apartment_number, "496")
        self.assertEqual(preview.inspection_date, date(2026, 11, 9))
        self.assertEqual([(r.point_number, r.description) for r in preview.remarks], [
            ("11", "Следы влаги в коридоре"),
            ("11", "Смещение перегородки от разбивочной оси между спальней и кухней на 30 мм"),
            ("17", "Требуется очистка и регулировка изделий ПВХ"),
            ("22", "Не закреплён хомут на стояке"),
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
