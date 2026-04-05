"""Tests to verify the index.html light theme CSS variables."""

import os
import re
import unittest


class TestIndexHTMLTheme(unittest.TestCase):
    """Verify that index.html uses the correct light-theme CSS variables."""

    @classmethod
    def setUpClass(cls):
        html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            cls.html_content = f.read()

        # Extract the :root block
        root_match = re.search(r":root\s*\{([^}]+)\}", cls.html_content)
        assert root_match, ":root CSS block not found in index.html"
        cls.root_block = root_match.group(1)

    def _get_var(self, name):
        """Extract a CSS variable value from the :root block."""
        match = re.search(rf"--{name}\s*:\s*([^;]+);", self.root_block)
        self.assertIsNotNone(match, f"CSS variable --{name} not found in :root")
        return match.group(1).strip()

    def test_background_color_is_white(self):
        self.assertEqual(self._get_var("bg"), "#ffffff")

    def test_text_color_is_dark(self):
        self.assertEqual(self._get_var("text"), "#1a1a1a")

    def test_card_background_is_light(self):
        self.assertEqual(self._get_var("card"), "#f5f5f7")

    def test_border_is_visible_on_white(self):
        self.assertEqual(self._get_var("border"), "#d0d0d0")

    def test_muted_has_sufficient_contrast(self):
        self.assertEqual(self._get_var("muted"), "#666")

    def test_dim_adjusted_for_light_theme(self):
        self.assertEqual(self._get_var("dim"), "#999")

    def test_no_hardcoded_dark_bg_in_body(self):
        """Ensure body uses var(--bg), not a hardcoded dark color."""
        body_match = re.search(r"body\s*\{[^}]*background:\s*([^;]+);", self.html_content)
        self.assertIsNotNone(body_match)
        self.assertIn("var(--bg)", body_match.group(1))

    def test_no_dark_background_in_root(self):
        """The old dark background #0f1117 should not appear in :root."""
        self.assertNotIn("#0f1117", self.root_block)

    def test_no_light_text_on_light_bg(self):
        """The old light text color #e0e0e0 should not appear in :root."""
        self.assertNotIn("#e0e0e0", self.root_block)


if __name__ == "__main__":
    unittest.main()
