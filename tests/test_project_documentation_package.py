from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "project_documentation"
DOCS_RU = ROOT / "project_documentation_ru"


class ProjectDocumentationPackageTests(unittest.TestCase):
    def test_documentation_package_contains_required_sections(self):
        required_files = [
            "README.md",
            "01_project_overview.md",
            "02_architecture.md",
            "03_deployment.md",
            "04_configuration.md",
            "05_tests.md",
            "06_security_audit_summary.md",
            "configs/env.example.safe",
            "configs/nginx-rate-limit.conf",
            "configs/gunicorn.service.notes.md",
        ]
        for relative_path in required_files:
            with self.subTest(relative_path=relative_path):
                path = DOCS / relative_path
                self.assertTrue(path.exists(), f"Missing documentation file: {relative_path}")
                self.assertGreater(path.stat().st_size, 0)

    def test_documentation_package_does_not_include_real_env_or_database_files(self):
        self._assert_docs_have_no_secrets(DOCS)

    def test_russian_documentation_package_contains_required_sections(self):
        required_files = [
            "README.md",
            "01_описание_проекта.md",
            "02_архитектура.md",
            "03_развертывание.md",
            "04_конфигурация.md",
            "05_автотесты.md",
            "06_краткий_аудит_безопасности.md",
            "configs/env.example.safe",
            "configs/nginx-rate-limit.conf",
            "configs/gunicorn.service.notes.md",
        ]
        for relative_path in required_files:
            with self.subTest(relative_path=relative_path):
                path = DOCS_RU / relative_path
                self.assertTrue(path.exists(), f"Missing Russian documentation file: {relative_path}")
                self.assertGreater(path.stat().st_size, 0)

    def test_russian_documentation_package_does_not_include_real_env_or_database_files(self):
        self._assert_docs_have_no_secrets(DOCS_RU)

    def _assert_docs_have_no_secrets(self, docs_path: Path):
        forbidden_names = {".env", "crm.sqlite", "service-account.json"}
        found_names = {path.name for path in docs_path.rglob("*") if path.is_file()}
        self.assertTrue(forbidden_names.isdisjoint(found_names))

        for path in docs_path.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("SECRET_KEY=change-me", text)
            self.assertNotIn("BEGIN PRIVATE KEY", text)


if __name__ == "__main__":
    unittest.main()
