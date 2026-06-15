import re
import pytest
from errex.patterns import match_pattern

@pytest.mark.parametrize("error_text,expected_title_fragment", [
    ("NullPointerException", "Java"),
    ("ClassCastException: java.lang.String cannot be cast to java.lang.Integer", "ClassCast"),
    ("ArrayIndexOutOfBoundsException: Index 5 out of bounds for length 3", "ArrayIndex"),
    ("Segmentation fault (core dumped)", "Segmentation"),
    ("undefined reference to 'pthread_create'", "undefined reference"),
    ("NoMethodError: undefined method 'upcase' for nil:NilClass", "NoMethodError"),
    ("NameError: uninitialized constant User::Admin", "uninitialized constant"),
    ("LoadError: cannot load such file -- active_record", "LoadError"),
])
def test_pattern_matches(error_text, expected_title_fragment):
    result = match_pattern(error_text)
    assert result is not None, f"No pattern matched: {error_text!r}"
    title, explanation = result
    assert expected_title_fragment in title
    assert not re.search(r'\{[0-9]\}', explanation), f"Unsubstituted placeholder in: {explanation[:100]}"
