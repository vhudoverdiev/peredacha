import unittest

from app.services.remark_format import (
    has_quoted_remark_text,
    remark_plain_text_html,
    remark_sentence_lines_html,
    remark_text_html,
)


class RemarkFormatContractsTests(unittest.TestCase):
    def test_quoted_fragments_are_escaped_and_rendered_with_strike_class(self):
        html = str(remark_text_html('Replace "broken handle <script>" before handover'))

        self.assertIn('<span class="remark-quoted-strike">', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("&#34;broken handle &lt;script&gt;&#34;", html)

    def test_sentence_lines_keep_original_text_but_split_readable_display_fragments(self):
        html = str(remark_sentence_lines_html('First visible remark. Second visible remark with "quoted part".'))

        self.assertEqual(html.count('class="remark-sentence-line"'), 2)
        self.assertIn("First visible remark.", html)
        self.assertIn("Second visible remark", html)
        self.assertIn('<span class="remark-quoted-strike">&#34;quoted part&#34;</span>', html)

    def test_empty_none_and_plain_text_are_stable_and_safe(self):
        self.assertEqual(str(remark_text_html(None)), "")
        self.assertEqual(str(remark_sentence_lines_html("")), "")
        self.assertEqual(str(remark_plain_text_html("plain <b>remark</b>")), "plain &lt;b&gt;remark&lt;/b&gt;")

    def test_quote_detection_handles_complete_pairs_only(self):
        self.assertTrue(has_quoted_remark_text('Needs "replacement"'))
        self.assertFalse(has_quoted_remark_text('Needs "replacement'))
        self.assertFalse(has_quoted_remark_text(None))


if __name__ == "__main__":
    unittest.main()
