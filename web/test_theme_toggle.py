"""Tests for dark/light theme toggle feature across all web UI pages."""
import os
import re

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Pages that should have full theme toggle support
FULL_THEME_PAGES = ["index.html", "login.html", "billing.html", "history.html", "feedback.html"]
# Pages with minimal theme support (just CSS vars, no toggle button)
MINIMAL_THEME_PAGES = ["sso-callback.html"]
ALL_PAGES = FULL_THEME_PAGES + MINIMAL_THEME_PAGES


def read_file(filename):
    path = os.path.join(STATIC_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_light_theme_css_variables_defined():
    """Every page must define [data-theme='light'] CSS variable overrides."""
    for page in ALL_PAGES:
        content = read_file(page)
        assert '[data-theme="light"]' in content, (
            f"{page} is missing [data-theme='light'] CSS variable definitions"
        )


def test_light_theme_has_bg_variable():
    """Light theme must override --bg with a light color."""
    for page in ALL_PAGES:
        content = read_file(page)
        # Find the [data-theme="light"] block and check it has --bg
        match = re.search(r'\[data-theme="light"\]\s*\{([^}]+)\}', content)
        assert match, f"{page} missing [data-theme='light'] block"
        block = match.group(1)
        assert "--bg:" in block, f"{page} light theme missing --bg variable"
        assert "--text:" in block, f"{page} light theme missing --text variable"


def test_theme_toggle_button_present():
    """Full theme pages must have a theme toggle button."""
    for page in FULL_THEME_PAGES:
        content = read_file(page)
        assert 'id="theme-toggle"' in content, (
            f"{page} is missing theme toggle button (id='theme-toggle')"
        )


def test_theme_toggle_css_present():
    """Full theme pages must have .theme-toggle-btn CSS."""
    for page in FULL_THEME_PAGES:
        content = read_file(page)
        assert ".theme-toggle-btn" in content, (
            f"{page} is missing .theme-toggle-btn CSS class"
        )


def test_theme_toggle_js_logic():
    """Full theme pages must have localStorage ta_theme toggle logic."""
    for page in FULL_THEME_PAGES:
        content = read_file(page)
        assert "ta_theme" in content, (
            f"{page} missing localStorage key 'ta_theme'"
        )
        assert "theme-toggle" in content, (
            f"{page} missing theme-toggle JS logic"
        )
        assert "data-theme" in content, (
            f"{page} missing data-theme attribute manipulation"
        )


def test_sso_callback_reads_theme():
    """SSO callback page should read theme from localStorage."""
    content = read_file("sso-callback.html")
    assert "ta_theme" in content, (
        "sso-callback.html should read ta_theme from localStorage"
    )


def test_dark_theme_is_default():
    """Dark theme variables must be in :root (the default)."""
    for page in ["index.html", "billing.html", "history.html", "feedback.html"]:
        content = read_file(page)
        match = re.search(r':root\s*\{([^}]+)\}', content)
        assert match, f"{page} missing :root CSS block"
        root_block = match.group(1)
        assert "--bg: #0f1117" in root_block or "--bg:#0f1117" in root_block, (
            f"{page} :root should have dark --bg as default"
        )


def test_no_theme_toggle_in_sso_callback():
    """SSO callback is transient; it should NOT have a toggle button."""
    content = read_file("sso-callback.html")
    assert 'id="theme-toggle"' not in content, (
        "sso-callback.html should not have a theme toggle button"
    )


def test_light_header_override():
    """Pages with headers should override the dark gradient in light mode."""
    for page in ["index.html", "billing.html", "history.html", "feedback.html"]:
        content = read_file(page)
        assert '[data-theme="light"] .header' in content, (
            f"{page} missing light mode header gradient override"
        )


if __name__ == "__main__":
    tests = [
        test_light_theme_css_variables_defined,
        test_light_theme_has_bg_variable,
        test_theme_toggle_button_present,
        test_theme_toggle_css_present,
        test_theme_toggle_js_logic,
        test_sso_callback_reads_theme,
        test_dark_theme_is_default,
        test_no_theme_toggle_in_sso_callback,
        test_light_header_override,
    ]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS: {test_fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test_fn.__name__} - {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test_fn.__name__} - {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} tests passed")
    if failed:
        exit(1)
