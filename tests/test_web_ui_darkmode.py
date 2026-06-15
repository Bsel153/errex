import errex.web_ui as _wu


def _get_html() -> str:
    """Return the main web UI HTML template directly from the module attribute."""
    return _wu.HTML


def test_html_template_is_nonempty():
    assert len(_get_html()) > 500


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
    assert 'EE0000' in html


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


def test_html_is_valid_doctype():
    assert _get_html().strip().startswith('<!DOCTYPE html>')


def test_dark_and_light_theme_both_present():
    html = _get_html()
    assert 'data-theme="dark"' in html or "[data-theme=\"dark\"]" in html



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
