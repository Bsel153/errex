import pytest
from unittest.mock import patch, MagicMock


def test_suggest_fixes_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from errex.suggest_fixes import suggest_fixes
    with pytest.raises(SystemExit):
        suggest_fixes()


def test_suggest_fixes_no_findings(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    from errex.scanners._base import ScanResult
    with patch("errex.scan.run_scan") as mock_scan, \
         patch("errex.scan.detect_platform", return_value="linux"):
        mock_scan.return_value = ScanResult(platform="linux", started_at="2026-01-01T00:00:00Z")
        from errex.suggest_fixes import suggest_fixes
        suggest_fixes(model="claude-sonnet-4-6")
