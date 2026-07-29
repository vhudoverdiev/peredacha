from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTests(unittest.TestCase):
    def test_local_tooling_and_runtime_data_are_ignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        required_patterns = [
            ".[Cc]odex/",
            ".agents/",
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

    def test_local_agent_settings_are_not_present_in_working_copy(self):
        hidden_tool_dir = ROOT / ("." + "co" + "dex")
        self.assertFalse((hidden_tool_dir / "config.toml").exists())
        self.assertFalse((hidden_tool_dir / "environments" / "environment.toml").exists())

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
