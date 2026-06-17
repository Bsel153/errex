import pytest
from unittest.mock import patch, MagicMock
from errex.review_pr import _parse_pr_url, _fetch_diff


def test_parse_full_url():
    result = _parse_pr_url("https://github.com/owner/repo/pull/42")
    assert result == ("owner", "repo", 42)


def test_parse_http_url():
    result = _parse_pr_url("http://github.com/acme/project/pull/1")
    assert result == ("acme", "project", 1)


def test_parse_shorthand():
    result = _parse_pr_url("owner/repo#99")
    assert result == ("owner", "repo", 99)


def test_parse_invalid():
    assert _parse_pr_url("not-a-pr-url") is None
    assert _parse_pr_url("https://example.com/foo") is None
    assert _parse_pr_url("") is None


def test_parse_trailing_path_not_matched():
    assert _parse_pr_url("https://github.com/a/b/issues/1") is None


def test_fetch_diff_sends_diff_accept_header():
    import io
    fake_resp = MagicMock()
    fake_resp.read.return_value = b"diff --git a/f.py b/f.py\n+hello"
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.review_pr.urllib.request.urlopen", return_value=fake_resp) as mock_open:
        result = _fetch_diff("owner", "repo", 1, token="tok123")

    req = mock_open.call_args[0][0]
    assert req.get_header("Accept") == "application/vnd.github.v3.diff"
    assert "tok123" in req.get_header("Authorization")
    assert "diff --git" in result


def test_fetch_diff_no_token():
    fake_resp = MagicMock()
    fake_resp.read.return_value = b"diff content"
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("errex.review_pr.urllib.request.urlopen", return_value=fake_resp) as mock_open:
        _fetch_diff("o", "r", 5, token=None)

    req = mock_open.call_args[0][0]
    assert not req.has_header("Authorization")
