"""Tests for the dark/light theme toggle feature."""
import os
import unittest

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Pages that should have the theme toggle button
PAGES_WITH_TOGGLE = ["index.html", "billing.html", "history.html", "feedback.html", "login.html"]

# All pages that should include theme.css and theme.js
ALL_PAGES = PAGES_WITH_TOGGLE + ["sso-callback.html"]


class TestThemeFiles(unittest.TestCase):
    """Verify theme.css and theme.js exist with required content."""

    def test_theme_css_exists(self):
        path = os.path.join(STATIC_DIR, "theme.css")
        self.assertTrue(os.path.isfile(path), "theme.css must exist")

    def test_theme_js_exists(self):
        path = os.path.join(STATIC_DIR, "theme.js")
        self.assertTrue(os.path.isfile(path), "theme.js must exist")

    def test_theme_css_has_dark_variables(self):
        with open(os.path.join(STATIC_DIR, "theme.css")) as f:
            css = f.read()
        self.assertIn('[data-theme="dark"]', css)
        self.assertIn("--bg:", css)
        self.assertIn("--header-bg:", css)

    def test_theme_css_has_light_variables(self):
        with open(os.path.join(STATIC_DIR, "theme.css")) as f:
            css = f.read()
        self.assertIn('[data-theme="light"]', css)
        # Light theme should use lighter background
        self.assertIn("#f5f6fa", css)

    def test_theme_css_has_switch_styles(self):
        with open(os.path.join(STATIC_DIR, "theme.css")) as f:
            css = f.read()
        self.assertIn(".theme-switch", css)

    def test_theme_js_uses_localstorage(self):
        with open(os.path.join(STATIC_DIR, "theme.js")) as f:
            js = f.read()
        self.assertIn("localStorage", js)
        self.assertIn("ta_theme", js)

    def test_theme_js_sets_data_attribute(self):
        with open(os.path.join(STATIC_DIR, "theme.js")) as f:
            js = f.read()
        self.assertIn("data-theme", js)

    def test_theme_js_references_buttons(self):
        with open(os.path.join(STATIC_DIR, "theme.js")) as f:
            js = f.read()
        self.assertIn("btn-theme-dark", js)
        self.assertIn("btn-theme-light", js)


class TestPagesIncludeTheme(unittest.TestCase):
    """Verify all pages load theme.css and theme.js."""

    def test_all_pages_link_theme_css(self):
        for page in ALL_PAGES:
            with open(os.path.join(STATIC_DIR, page)) as f:
                html = f.read()
            self.assertIn("theme.css", html, f"{page} must include theme.css")

    def test_all_pages_load_theme_js(self):
        for page in ALL_PAGES:
            with open(os.path.join(STATIC_DIR, page)) as f:
                html = f.read()
            self.assertIn("theme.js", html, f"{page} must include theme.js")


class TestThemeToggleButton(unittest.TestCase):
    """Verify pages with headers have the theme toggle buttons."""

    def test_pages_have_dark_button(self):
        for page in PAGES_WITH_TOGGLE:
            with open(os.path.join(STATIC_DIR, page)) as f:
                html = f.read()
            self.assertIn("btn-theme-dark", html, f"{page} must have dark mode button")

    def test_pages_have_light_button(self):
        for page in PAGES_WITH_TOGGLE:
            with open(os.path.join(STATIC_DIR, page)) as f:
                html = f.read()
            self.assertIn("btn-theme-light", html, f"{page} must have light mode button")

    def test_pages_have_theme_switch_container(self):
        for page in PAGES_WITH_TOGGLE:
            with open(os.path.join(STATIC_DIR, page)) as f:
                html = f.read()
            self.assertIn("theme-switch", html, f"{page} must have theme-switch container")


class TestThemeVariableUsage(unittest.TestCase):
    """Verify pages use CSS variables instead of hardcoded colors for key properties."""

    def test_header_uses_variable_background(self):
        """Header background should use var(--header-bg), not hardcoded gradient."""
        for page in ["index.html", "billing.html", "history.html", "feedback.html"]:
            with open(os.path.join(STATIC_DIR, page)) as f:
                html = f.read()
            self.assertIn("var(--header-bg)", html, f"{page} header should use --header-bg variable")

    def test_header_title_uses_variable_color(self):
        """Header h1 should use var(--header-text), not hardcoded #fff."""
        for page in ["index.html", "billing.html", "history.html", "feedback.html"]:
            with open(os.path.join(STATIC_DIR, page)) as f:
                html = f.read()
            self.assertIn("var(--header-text)", html, f"{page} header title should use --header-text variable")

    def test_no_hardcoded_root_variables_in_main_pages(self):
        """Pages with header should NOT re-define :root color variables (they come from theme.css)."""
        for page in ["index.html", "billing.html", "history.html"]:
            with open(os.path.join(STATIC_DIR, page)) as f:
                html = f.read()
            # Should not contain the old :root block with --bg: #0f1117
            self.assertNotIn(":root {", html, f"{page} should not re-define :root variables (use theme.css)")


class TestLightThemeColors(unittest.TestCase):
    """Verify light theme provides appropriate light-mode colors."""

    def test_light_bg_is_light(self):
        with open(os.path.join(STATIC_DIR, "theme.css")) as f:
            css = f.read()
        # Extract light section
        light_idx = css.index('[data-theme="light"]')
        light_section = css[light_idx:css.index("}", light_idx) + 1]
        # Background should be a light color
        self.assertIn("#f5f6fa", light_section)

    def test_light_card_is_white(self):
        with open(os.path.join(STATIC_DIR, "theme.css")) as f:
            css = f.read()
        light_idx = css.index('[data-theme="light"]')
        light_section = css[light_idx:css.index("}", light_idx) + 1]
        self.assertIn("#ffffff", light_section)

    def test_light_text_is_dark(self):
        with open(os.path.join(STATIC_DIR, "theme.css")) as f:
            css = f.read()
        light_idx = css.index('[data-theme="light"]')
        light_section = css[light_idx:css.index("}", light_idx) + 1]
        self.assertIn("#1a1a2e", light_section)


if __name__ == "__main__":
    unittest.main()
