from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTests(unittest.TestCase):
    def test_local_tooling_and_runtime_data_are_ignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        required_patterns = [
            "venv/",
            ".env",
            "instance/*.sqlite",
            "instance/*.db",
            "uploads/*",
            "exports/*",
            "*.zip",
        ]
        gitignore_lines = set(gitignore.splitlines())
        for pattern in required_patterns:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore_lines)

        obsolete_patterns = [
            "node_modules/",
            ".agents/",
            "tmp_preview/",
            "tmp_video_frames/",
            "temp_preview/",
            "tmp_dashboard_*.png",
            "tmp_*.html",
        ]
        for pattern in obsolete_patterns:
            with self.subTest(obsolete_pattern=pattern):
                self.assertNotIn(pattern, gitignore_lines)

    def test_obsolete_root_documents_are_not_present(self):
        obsolete_files = [
            "CHANGELOG_LOCAL.md",
            "SECURITY_AUDIT_2026-07-29.md",
        ]
        for relative_path in obsolete_files:
            with self.subTest(relative_path=relative_path):
                self.assertFalse((ROOT / relative_path).exists())

    def test_repository_files_do_not_contain_tool_brand_name(self):
        forbidden = "co" + "dex"
        searchable_extensions = {".py", ".md", ".txt", ".toml", ".env", ".conf", ".service", ".socket", ".html", ".css", ".js"}
        ignored_parts = {".git", "venv", ".venv", "env", "instance", "uploads", "exports"}
        for path in ROOT.rglob("*"):
            if any(part in ignored_parts for part in path.parts):
                continue
            relative_path = str(path.relative_to(ROOT)).casefold()
            self.assertNotIn(forbidden, relative_path)
            if not path.is_file() or path.suffix.lower() not in searchable_extensions:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").casefold()
            self.assertNotIn(forbidden, text, str(path.relative_to(ROOT)))


if __name__ == "__main__":
    unittest.main()
