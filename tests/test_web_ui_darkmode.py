import re


def _get_html():
    import errex.web_ui as wu
    # Extract the HTML string from the module
    src = open(wu.__file__).read()
    # Find the HTML template
    m = re.search(r'"""(<!DOCTYPE html>.*?)"""', src, re.DOTALL)
    if not m:
        m = re.search(r"'''(<!DOCTYPE html>.*?)'''", src, re.DOTALL)
    return m.group(1) if m else ""


def test_dark_mode_css_variables_defined():
    html = _get_html()
    assert '--bg:' in html or '--bg :' in html
    assert 'data-theme' in html


def test_dark_theme_block_exists():
    html = _get_html()
    assert '[data-theme="dark"]' in html


def test_theme_toggle_button_exists():
    html = _get_html()
    assert 'theme-toggle' in html
    assert 'toggleTheme' in html


def test_toggle_theme_js_exists():
    html = _get_html()
    assert 'function toggleTheme' in html
    assert 'localStorage' in html


def test_rht_red_accent():
    html = _get_html()
    assert '#EE0000' in html or 'EE0000' in html


def test_red_hat_font():
    html = _get_html()
    assert 'Red Hat' in html

def test_textsize_toggle_button_exists():
    html = _get_html()
    assert 'textsize-toggle' in html
    assert 'toggleTextSize' in html


def test_textsize_css_rule_exists():
    html = _get_html()
    assert '[data-textsize="large"]' in html


def test_toggle_textsize_js_persists_to_localstorage():
    html = _get_html()
    assert 'function toggleTextSize' in html
    assert 'errex-textsize' in html
