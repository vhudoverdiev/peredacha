from datetime import datetime
import unittest
from unittest.mock import patch

from app.services import document_flow


class DocumentFlowContractsTests(unittest.TestCase):
    def test_safe_docx_filename_sanitizes_stem_and_uses_deterministic_timestamp(self):
        class FixedDatetime:
            @classmethod
            def now(cls):
                return datetime(2026, 7, 29, 12, 34, 56)

        with patch("app.services.document_flow.datetime", FixedDatetime):
            filename = document_flow.safe_docx_filename(' ../bad:name?.docx ', prefix="fallback")

        self.assertEqual(filename, "bad_name_20260729_123456.docx")

    def test_basic_field_normalizers_are_idempotent_and_apply_business_prefixes(self):
        self.assertEqual(document_flow._normalize_owner_count("2"), "2")
        self.assertEqual(document_flow._normalize_owner_count("unexpected"), "1")
        self.assertEqual(document_flow._normalize_owner_gender("male"), "male")
        self.assertEqual(document_flow._normalize_owner_gender("unknown", default="female"), "female")
        self.assertEqual(document_flow._normalize_apartment_number("15"), "№ 15")
        self.assertEqual(document_flow._normalize_apartment_number("№ 15"), "№ 15")
        self.assertTrue(document_flow._normalize_floor_text("7").startswith("7 "))
        self.assertEqual(document_flow._normalize_contract_text("MIR/1 2026"), "№ MIR/1 2026 года")

    def test_signature_block_adds_missing_signature_prefix_and_preserves_existing_lines(self):
        normalized = document_flow._normalize_signature_block("Ivanov I.I.\n___________________/Petrov P.P.\n")

        self.assertEqual(normalized, "___________________/Ivanov I.I.\n___________________/Petrov P.P.")

    def test_normalize_fields_handles_single_and_second_owner_contract_defaults(self):
        normalized = document_flow._normalize_fields({
            "owner_count": "1",
            "owner_one_gender": "male",
            "apartment_number": "8",
            "floor_number": "2",
            "contract_full": "MIR/1 2026",
            "creditor_signatures": "Manual Person",
        })

        self.assertEqual(normalized["owner_count"], "1")
        self.assertEqual(normalized["owner_one_gender"], "male")
        self.assertEqual(normalized["owner_two_data"], "")
        self.assertEqual(normalized["apartment_number"], "№ 8")
        self.assertTrue(normalized["floor_number"].startswith("2 "))
        self.assertEqual(normalized["contract_full"], "№ MIR/1 2026 года")
        self.assertEqual(normalized["creditor_signatures"], "___________________/Manual Person")

    def test_build_replacements_supports_multiple_placeholder_styles_and_labels(self):
        replacements = document_flow._build_replacements({
            "contract_full": "в„– MIR/1",
            "apartment_number": "в„– 8",
        })

        self.assertEqual(replacements["{{contract_full}}"], "в„– MIR/1")
        self.assertEqual(replacements["[contract_full]"], "в„– MIR/1")
        self.assertEqual(replacements["{{APARTMENT_NUMBER}}"], "в„– 8")
        self.assertEqual(replacements["[APARTMENT NUMBER]"], "в„– 8")

    def test_word_xml_filter_only_allows_editable_word_document_parts(self):
        self.assertTrue(document_flow._is_word_xml("word/document.xml"))
        self.assertTrue(document_flow._is_word_xml("word/header1.xml"))
        self.assertTrue(document_flow._is_word_xml("word/footer2.xml"))
        self.assertFalse(document_flow._is_word_xml("word/styles.xml"))
        self.assertFalse(document_flow._is_word_xml("docProps/core.xml"))


if __name__ == "__main__":
    unittest.main()
