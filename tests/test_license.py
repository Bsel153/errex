"""Tests for license key validation."""
from errex.license import validate_key, activate, is_pro, _sign


def test_valid_pro_key():
    from datetime import date
    today = date.today()
    # Future expiry
    exp_year = today.year + 1
    expiry = f"{exp_year}{today.month:02d}"
    sig = _sign(f"pro:{expiry}")
    key = f"ERREX-PRO-{expiry}-{sig}"
    info = validate_key(key)
    assert info is not None
    assert info["tier"] == "pro"
    assert info["valid"] is True
    assert info["expired"] is False


def test_invalid_key_returns_none():
    assert validate_key("ERREX-PRO-999999-AAAAAAAA") is None
    assert validate_key("NOTAKEY") is None
    assert validate_key("") is None


def test_expired_key():
    expiry = "202001"  # January 2020 — definitely expired
    sig = _sign(f"pro:{expiry}")
    key = f"ERREX-PRO-{expiry}-{sig}"
    info = validate_key(key)
    assert info is not None
    assert info["expired"] is True
    assert info["valid"] is False


def test_wrong_hmac_invalid():
    from datetime import date
    today = date.today()
    expiry = f"{today.year + 1}{today.month:02d}"
    key = f"ERREX-PRO-{expiry}-AAAAAAAA"  # wrong sig
    assert validate_key(key) is None


def test_activate_saves_key(tmp_path, monkeypatch):
    import errex.license as lic
    monkeypatch.setattr(lic, "_CONFIG_FILE", tmp_path / ".errex.json")
    from datetime import date
    today = date.today()
    expiry = f"{today.year + 1}{today.month:02d}"
    sig = _sign(f"pro:{expiry}")
    key = f"ERREX-PRO-{expiry}-{sig}"
    result = activate(key)
    assert result["success"] is True
    assert result["tier"] == "pro"


def test_activate_invalid_key(tmp_path, monkeypatch):
    import errex.license as lic
    monkeypatch.setattr(lic, "_CONFIG_FILE", tmp_path / ".errex.json")
    result = activate("ERREX-PRO-202601-AAAAAAAA")
    assert result["success"] is False
    assert "Invalid" in result["error"]
