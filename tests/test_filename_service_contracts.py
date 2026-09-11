import unittest

from app.services.filename import safe_filename_part


class FilenameServiceContractsTests(unittest.TestCase):
    def test_safe_filename_part_strips_forbidden_characters_and_collapses_spaces(self):
        self.assertEqual(safe_filename_part('  A/B:C*D?"E<>|  '), "A B C D E")

    def test_safe_filename_part_uses_caller_fallback_for_empty_values(self):
        self.assertEqual(safe_filename_part("  ", fallback="object"), "object")
        self.assertEqual(safe_filename_part(None), "export")


if __name__ == "__main__":
    unittest.main()
