import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_DETAIL = PROJECT_ROOT / "app" / "templates" / "task_detail.html"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
MOBILE_CSS = PROJECT_ROOT / "app" / "static" / "mobile-only.css"


class TaskCommentHoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task_detail = TASK_DETAIL.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")

    def test_comment_form_has_a_stable_scoped_hook(self):
        self.assertIn('data-task-comment-async="1"', self.task_detail)
        self.assertIn('comment_form.submit(class="btn btn-outline-primary")', self.task_detail)

    def test_desktop_hover_uses_help_green_and_black_text(self):
        scoped_hook = '.task-detail-comments-card form[data-task-comment-async="1"]'
        hook_start = self.desktop_css.index(scoped_hook)
        start = self.desktop_css.index('.btn:is(:hover, :focus-visible)', hook_start)
        end = self.desktop_css.index("}", start)
        rule = self.desktop_css[start:end]
        scope = self.desktop_css[hook_start - 120:start]

        self.assertIn("html.desktop-like-pointer", scope)
        self.assertIn(".task-detail-comments-card", scope)
        self.assertIn('form[data-task-comment-async="1"]', scope)
        self.assertIn("var(--peredacha-action-green)", rule)
        self.assertIn("var(--peredacha-action-green-hover)", rule)
        self.assertIn("color: #000000 !important", rule)
        self.assertIn("-webkit-text-fill-color: #000000 !important", rule)

    def test_mobile_styles_are_untouched(self):
        start = self.mobile_css.index(
            "body.app-body:has(.task-detail-page) .task-detail-comments-card"
        )
        end = self.mobile_css.index("}", start)
        rule = self.mobile_css[start:end]

        self.assertIn("color: #fff !important", rule)
        self.assertNotIn("#000000", rule)


if __name__ == "__main__":
    unittest.main()
