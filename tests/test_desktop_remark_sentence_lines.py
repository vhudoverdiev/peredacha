import html
import re
import unittest
from pathlib import Path

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, Project, ROLE_ADMIN, Task, User, WorkPoint
from app.services.remark_format import remark_plain_text_html, remark_sentence_lines_html


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
MOBILE_CSS = PROJECT_ROOT / "app" / "static" / "mobile-only.css"
SCRIPT_PATH = PROJECT_ROOT / "app" / "static" / "script.js"

DESKTOP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
MOBILE_USER_AGENT = "Mozilla/5.0 (Linux; Android 15; Mobile)"


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "desktop-remark-sentence-lines-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


def markup_text(value: object) -> str:
    without_tags = re.sub(r"<[^>]+>", "", str(value))
    return html.unescape(without_tags)


class RemarkSentenceFormatterTests(unittest.TestCase):
    def test_sentences_are_separate_visual_lines_without_mutating_source_text(self):
        source = (
            "Окалины снаружи. Требуется регулировка створок. "
            "Отсутствует стих в монтажном шве."
        )
        rendered = remark_sentence_lines_html(source)

        self.assertEqual(str(rendered).count('class="remark-sentence-line"'), 3)
        self.assertEqual(markup_text(rendered), source)

    def test_dates_decimals_abbreviations_and_numbered_prefixes_are_not_split_inside(self):
        source = (
            "В т.ч. требуется профиль. Дата 01.08.2026. "
            "Размер 1.5 мм. 1. Отдельное замечание."
        )
        rendered = remark_sentence_lines_html(source)

        self.assertEqual(str(rendered).count('class="remark-sentence-line"'), 3)
        self.assertIn("В т.ч. требуется профиль.", str(rendered))
        self.assertIn("01.08.2026.", str(rendered))
        self.assertIn("1.5 мм.", str(rendered))
        self.assertIn("1. Отдельное замечание.", str(rendered))
        self.assertEqual(markup_text(rendered), source)

    def test_sentence_starting_with_uppercase_is_split_even_without_space(self):
        source = "Первая часть.Окалины снаружи;Требуется регулировка."
        rendered = remark_sentence_lines_html(source)

        self.assertEqual(str(rendered).count('class="remark-sentence-line"'), 3)
        self.assertEqual(markup_text(rendered), source)

    def test_short_work_abbreviations_do_not_become_visual_lines(self):
        for source in ("отст.ХГВС", "отст. ХГВС", "отсут.ХГВС", "Повреж.МДФ"):
            with self.subTest(source=source):
                rendered = remark_sentence_lines_html(source)

                self.assertNotIn('class="remark-sentence-line"', str(rendered))
                self.assertEqual(markup_text(rendered), source)

    def test_semicolon_splits_only_when_both_sides_are_meaningful(self):
        short_source = "МДФ;ХГВС"
        long_source = "Длинная первая часть;Вторая часть"

        self.assertNotIn('class="remark-sentence-line"', str(remark_sentence_lines_html(short_source)))
        self.assertEqual(
            str(remark_sentence_lines_html(long_source)).count('class="remark-sentence-line"'),
            2,
        )

    def test_plain_filter_keeps_dop_agreement_text_in_one_visual_block(self):
        source = "Первая длинная часть. Вторая длинная часть;Третья длинная часть"
        rendered = remark_plain_text_html(source)

        self.assertNotIn('class="remark-sentence-line"', str(rendered))
        self.assertEqual(markup_text(rendered), source)

    def test_escaping_and_quoted_strike_survive_sentence_formatting(self):
        source = 'Опасный <тег>. "Выполнено. Проверено." Следующее замечание.'
        rendered = remark_sentence_lines_html(source)
        rendered_html = str(rendered)

        self.assertNotIn("<тег>", rendered_html)
        self.assertIn("&lt;тег&gt;", rendered_html)
        self.assertIn('class="remark-quoted-strike"', rendered_html)
        self.assertEqual(markup_text(rendered), source)


class RemarkSentenceSiteIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        project = Project(name="Remark sentence lines QA")
        user = User(
            username="remark-sentence-admin",
            password_hash="unused",
            role=ROLE_ADMIN,
            all_projects_access=True,
        )
        apartment = Apartment(project=project, apartment_number="12")
        work_point = WorkPoint(point_number="16", source_sheet_name="qa")
        task = Task(
            source_uid="remark-sentence-task",
            project=project,
            apartment=apartment,
            work_point=work_point,
            description="Первое замечание. Второе замечание.",
        )
        db.session.add_all([project, user, apartment, work_point, task])
        db.session.commit()
        self.task_id = task.id

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
            session["session_version"] = int(user.session_version or 0)
            session["current_project_id"] = project.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def test_desktop_and_mobile_use_sentence_lines(self):
        desktop_response = self.client.get(
            f"/tasks/{self.task_id}",
            headers={"User-Agent": DESKTOP_USER_AGENT},
        )
        mobile_response = self.client.get(
            f"/tasks/{self.task_id}",
            headers={"User-Agent": MOBILE_USER_AGENT},
        )
        desktop_page = desktop_response.get_data(as_text=True)
        mobile_page = mobile_response.get_data(as_text=True)

        self.assertEqual(desktop_response.status_code, 200)
        self.assertEqual(mobile_response.status_code, 200)
        self.assertEqual(desktop_page.count('class="remark-sentence-line"'), 2)
        self.assertEqual(mobile_page.count('class="remark-sentence-line"'), 2)

    def test_css_and_dynamic_rendering_cover_desktop_and_mobile(self):
        desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        script = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertRegex(
            desktop_css,
            r"html\.desktop-like-pointer \.remark-sentence-line\s*\{\s*display: block;",
        )
        self.assertRegex(
            mobile_css,
            r"\.remark-sentence-line\s*\{\s*display: block;",
        )
        self.assertIn("const remarkSentenceRanges", script)
        self.assertIn("const sentenceRanges = remarkSentenceRanges(text);", script)
        self.assertIn("${formatGlassManualRemarkHtml(data.description || '')}", script)
        self.assertIn("currentNode.matches?.('.inline-text')", script)
        self.assertIn("currentNode.replaceChildren(", script)


if __name__ == "__main__":
    unittest.main()
