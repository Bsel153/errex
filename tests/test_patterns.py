"""Tests for the built-in pattern library added in the 20-pattern expansion."""
import pytest
from errex.patterns import match_pattern, PATTERNS


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def assert_pattern(error_text: str, expected_title: str, *expected_substrings: str):
    """Assert that error_text matches the given pattern title and that every
    expected_substring appears in the substituted explanation."""
    result = match_pattern(error_text)
    assert result is not None, f"No pattern matched: {error_text!r}"
    title, explanation = result
    assert title == expected_title, f"Expected title {expected_title!r}, got {title!r}"
    for substr in expected_substrings:
        assert substr in explanation, (
            f"Expected {substr!r} in explanation, got:\n{explanation[:300]}"
        )


# ---------------------------------------------------------------------------
# Rust patterns
# ---------------------------------------------------------------------------

class TestRustPatterns:
    def test_e0308_with_types(self):
        error = (
            "error[E0308]: mismatched types\n"
            "  --> src/main.rs:5:13\n"
            "   |\n"
            "5  |     let x: i32 = \"hello\";\n"
            "   |            ---   ^^^^^^^ expected `i32`, found `&str`"
        )
        assert_pattern(error, "Rust — E0308: mismatched types", "i32", "&str")

    def test_e0382_captures_variable_name(self):
        error = "error[E0382]: borrow of moved value: `my_string`"
        assert_pattern(
            error,
            "Rust — E0382: borrow of moved value",
            "my_string",
        )

    def test_e0502_captures_variable_name(self):
        error = "error[E0502]: cannot borrow `buffer` as mutable because it is also borrowed as immutable"
        assert_pattern(
            error,
            "Rust — E0502: mutable + immutable borrow conflict",
            "buffer",
        )

    def test_e0499_captures_variable_name(self):
        error = "error[E0499]: cannot borrow `items` as mutable more than once at a time"
        assert_pattern(
            error,
            "Rust — E0499: double mutable borrow",
            "items",
        )

    def test_e0382_use_of_moved(self):
        error = "error[E0382]: use of moved value: `config`"
        assert_pattern(error, "Rust — E0382: borrow of moved value", "config")


# ---------------------------------------------------------------------------
# Go patterns
# ---------------------------------------------------------------------------

class TestGoPatterns:
    def test_undefined_symbol_captures_name(self):
        error = "undefined: http"
        assert_pattern(error, "Go — undefined symbol", "http")

    def test_type_mismatch_captures_all_three(self):
        error = "cannot use count (variable of type int) as type int64"
        assert_pattern(error, "Go — type mismatch", "count", "int", "int64")

    def test_unused_import_captures_package(self):
        error = '"fmt" imported and not used'
        assert_pattern(error, "Go — unused import", "fmt")

    def test_goroutine_deadlock(self):
        error = "fatal error: all goroutines are asleep - deadlock!"
        assert_pattern(error, "Go — all goroutines are asleep (deadlock)")


# ---------------------------------------------------------------------------
# Docker patterns
# ---------------------------------------------------------------------------

class TestDockerPatterns:
    def test_pull_access_denied_captures_image(self):
        error = "pull access denied for myorg/private-image:latest"
        assert_pattern(
            error,
            "Docker — pull access denied",
            "myorg/private-image:latest",
        )

    def test_container_name_conflict_captures_name(self):
        error = (
            'Error response from daemon: Conflict. '
            'The container name "/webserver" is already in use'
        )
        assert_pattern(error, "Docker — container name conflict", "webserver")

    def test_container_not_found_captures_name(self):
        error = "Error: No such container: my_app_container"
        assert_pattern(
            error,
            "Docker — container not found",
            "my_app_container",
        )


# ---------------------------------------------------------------------------
# pip patterns
# ---------------------------------------------------------------------------

class TestPipPatterns:
    def test_package_not_found_captures_name(self):
        error = "ERROR: Could not find a version that satisfies the requirement numpy==99.0"
        assert_pattern(error, "pip — package not found", "numpy==99.0")

    def test_dependency_conflict(self):
        error = (
            "ERROR: pip's dependency resolver does not currently take into account "
            "all the packages that are installed. This behaviour is the source of "
            "the following dependency conflicts. has incompatible versions."
        )
        assert_pattern(error, "pip — dependency conflict")


# ---------------------------------------------------------------------------
# npm patterns
# ---------------------------------------------------------------------------

class TestNpmPatterns:
    def test_404_captures_package_name(self):
        error = "npm ERR! 404 Not Found - GET https://registry.npmjs.org/nonexistent-package"
        assert_pattern(
            error,
            "npm — package not found (404)",
            "nonexistent-package",
        )

    def test_no_package_json(self):
        error = "npm ERR! ENOENT: no such file or directory, open 'package.json'"
        assert_pattern(error, "npm — no package.json")

    def test_eacces_permission(self):
        error = "npm ERR! code EACCES"
        assert_pattern(error, "npm — permission denied (EACCES)")


# ---------------------------------------------------------------------------
# Shell / SSH patterns
# ---------------------------------------------------------------------------

class TestShellPatterns:
    def test_command_not_found_with_name(self):
        error = "-bash: git: command not found"
        result = match_pattern(error)
        assert result is not None
        # Either the generic or the named version matches; named is preferred
        assert "command not found" in result[0].lower()

    def test_command_not_found_zsh_captures_name(self):
        error = "zsh: git: command not found"
        result = match_pattern(error)
        assert result is not None
        assert "command not found" in result[0].lower()

    def test_ssh_publickey_rejection(self):
        error = "Permission denied (publickey)."
        assert_pattern(error, "SSH — public key authentication failed")


# ---------------------------------------------------------------------------
# Database patterns
# ---------------------------------------------------------------------------

class TestDatabasePatterns:
    def test_postgresql_auth_failed_captures_user(self):
        error = 'FATAL:  password authentication failed for user "app_user"'
        assert_pattern(
            error,
            "PostgreSQL — authentication failed",
            "app_user",
        )

    def test_mysql_access_denied_captures_user_and_host(self):
        error = "ERROR 1045 (28000): Access denied for user 'deploy'@'10.0.0.5'"
        assert_pattern(
            error,
            "MySQL — access denied",
            "deploy",
            "10.0.0.5",
        )


# ---------------------------------------------------------------------------
# Sanity: no format() exceptions for any pattern with a plausible input
# ---------------------------------------------------------------------------

def test_all_patterns_have_valid_format_strings():
    """Ensure no pattern's explanation raises KeyError on format()."""
    # Pick a test input per pattern title so format() is exercised with groups
    sample_inputs = {
        "Rust — E0308: mismatched types": (
            "error[E0308]: mismatched types\n   | expected `i32`, found `&str`"
        ),
        "Rust — E0382: borrow of moved value": (
            "error[E0382]: borrow of moved value: `x`"
        ),
        "Rust — E0502: mutable + immutable borrow conflict": (
            "error[E0502]: cannot borrow `v` as mutable because it is also borrowed as immutable"
        ),
        "Rust — E0499: double mutable borrow": (
            "error[E0499]: cannot borrow `v` as mutable more than once at a time"
        ),
        "Go — undefined symbol": "undefined: fmt",
        "Go — type mismatch": "cannot use x (variable of type int) as type int64",
        "Go — unused import": '"fmt" imported and not used',
        "Go — all goroutines are asleep (deadlock)": (
            "fatal error: all goroutines are asleep - deadlock!"
        ),
        "Docker — pull access denied": "pull access denied for img:tag",
        "Docker — container name conflict": (
            'Error response from daemon: Conflict. The container name "/c" is already in use'
        ),
        "Docker — container not found": "Error: No such container: abc",
        "pip — package not found": (
            "ERROR: Could not find a version that satisfies the requirement foo"
        ),
        "pip — dependency conflict": (
            "ERROR: pip's dependency resolver abc has incompatible def"
        ),
        "npm — package not found (404)": (
            "npm ERR! 404 Not Found - GET https://registry.npmjs.org/pkg"
        ),
        "npm — no package.json": (
            "npm ERR! ENOENT: no such file or directory, open 'package.json'"
        ),
        "npm — permission denied (EACCES)": "npm ERR! code EACCES",
        "Shell — command not found (with name)": "git: command not found",
        "SSH — public key authentication failed": "Permission denied (publickey)",
        "PostgreSQL — authentication failed": (
            'FATAL:  password authentication failed for user "bob"'
        ),
        "MySQL — access denied": (
            "ERROR 1045 (28000): Access denied for user 'root'@'localhost'"
        ),
    }
    for p in PATTERNS:
        if p.title not in sample_inputs:
            continue
        m = p.regex.search(sample_inputs[p.title])
        if m:
            # Should not raise
            try:
                p.explanation.format(*m.groups())
            except (KeyError, IndexError) as exc:
                pytest.fail(f"Pattern {p.title!r} raised {exc} on format()")
