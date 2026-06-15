"""Tests for errex/scanners/network.py — LAN device discovery and security checks."""
from __future__ import annotations

import socket
import subprocess
from unittest.mock import MagicMock, patch, call

import pytest

from errex.scanners.network import (
    _arp_table,
    _ssdp_discover,
    _open_ports,
    _check_default_creds,
    _tls_expiry_days,
    _mqtt_unauthenticated,
    get_findings,
)


# ── _arp_table ─────────────────────────────────────────────────────────────────


def test_arp_table_parses_standard_line(monkeypatch):
    result = MagicMock()
    result.stdout = "? (192.168.1.1) at aa:bb:cc:dd:ee:ff on en0\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

    devices = _arp_table()
    assert len(devices) == 1
    assert devices[0]["ip"] == "192.168.1.1"
    assert devices[0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert devices[0]["hostname"] == "?"


def test_arp_table_parses_hostname(monkeypatch):
    result = MagicMock()
    result.stdout = "router.local (192.168.1.254) at aa:00:11:22:33:44 on en0\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

    devices = _arp_table()
    assert len(devices) == 1
    assert devices[0]["hostname"] == "router.local"
    assert devices[0]["ip"] == "192.168.1.254"
    assert devices[0]["mac"] == "aa:00:11:22:33:44"


def test_arp_table_lowercases_mac(monkeypatch):
    result = MagicMock()
    result.stdout = "host (10.0.0.1) at AA:BB:CC:DD:EE:FF on eth0\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

    devices = _arp_table()
    assert devices[0]["mac"] == "aa:bb:cc:dd:ee:ff"


def test_arp_table_multiple_devices(monkeypatch):
    result = MagicMock()
    result.stdout = (
        "? (192.168.1.1) at aa:bb:cc:dd:ee:ff on en0\n"
        "device (192.168.1.2) at 11:22:33:44:55:66 on en0\n"
        "another (192.168.1.3) at de:ad:be:ef:00:01 on en0\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

    devices = _arp_table()
    assert len(devices) == 3
    ips = {d["ip"] for d in devices}
    assert ips == {"192.168.1.1", "192.168.1.2", "192.168.1.3"}


def test_arp_table_skips_incomplete_lines(monkeypatch):
    result = MagicMock()
    result.stdout = (
        "? (192.168.1.1) at aa:bb:cc:dd:ee:ff on en0\n"
        "incomplete line\n"
        "no ip here at ff:ff:ff:ff:ff:ff\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

    devices = _arp_table()
    assert len(devices) == 1
    assert devices[0]["ip"] == "192.168.1.1"


def test_arp_table_empty_stdout(monkeypatch):
    result = MagicMock()
    result.stdout = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

    assert _arp_table() == []


def test_arp_table_subprocess_raises(monkeypatch):
    def boom(*a, **kw):
        raise OSError("arp not found")

    monkeypatch.setattr(subprocess, "run", boom)
    assert _arp_table() == []


def test_arp_table_subprocess_timeout(monkeypatch):
    def boom(*a, **kw):
        raise subprocess.TimeoutExpired("arp", 5)

    monkeypatch.setattr(subprocess, "run", boom)
    assert _arp_table() == []


# ── _ssdp_discover ─────────────────────────────────────────────────────────────


class _MockSockAlwaysRaises:
    """Socket stub that raises on the first recv so the loop exits immediately."""

    def setsockopt(self, *a): pass
    def settimeout(self, t): pass
    def sendto(self, data, addr): pass
    def recvfrom(self, size): raise socket.timeout("timed out")
    def close(self): pass


class _MockSockOSError:
    """Socket stub that raises OSError on sendto to exercise the outer except."""

    def setsockopt(self, *a): pass
    def settimeout(self, t): pass
    def sendto(self, data, addr): raise OSError("network unreachable")
    def recvfrom(self, size): raise socket.timeout()
    def close(self): pass


def test_ssdp_discover_returns_empty_on_immediate_timeout(monkeypatch):
    def fake_socket(*a, **kw):
        return _MockSockAlwaysRaises()

    monkeypatch.setattr(socket, "socket", fake_socket)
    # Use a very small timeout so the monotonic loop is skipped
    result = _ssdp_discover(timeout=0.0)
    assert result == []


def test_ssdp_discover_returns_empty_on_socket_error(monkeypatch):
    def fake_socket(*a, **kw):
        return _MockSockOSError()

    monkeypatch.setattr(socket, "socket", fake_socket)
    result = _ssdp_discover(timeout=0.0)
    assert result == []


def test_ssdp_discover_socket_constructor_raises(monkeypatch):
    def boom(*a, **kw):
        raise OSError("permission denied")

    monkeypatch.setattr(socket, "socket", boom)
    result = _ssdp_discover(timeout=1.0)
    assert result == []


def test_ssdp_discover_parses_server_header(monkeypatch):
    """Mock a socket that returns one valid SSDP response then times out."""
    response_data = (
        b"HTTP/1.1 200 OK\r\n"
        b"SERVER: Linux/4.9 UPnP/1.1 MiniUPnPd/2.1\r\n"
        b"USN: uuid:abc123\r\n\r\n"
    )
    calls = {"n": 0}

    class _MockSockOneReply:
        def setsockopt(self, *a): pass
        def settimeout(self, t): pass
        def sendto(self, data, addr): pass

        def recvfrom(self, size):
            if calls["n"] == 0:
                calls["n"] += 1
                return (response_data, ("192.168.1.50", 1900))
            raise socket.timeout("done")

        def close(self): pass

    monkeypatch.setattr(socket, "socket", lambda *a, **kw: _MockSockOneReply())
    result = _ssdp_discover(timeout=0.1)
    assert len(result) == 1
    assert result[0]["ip"] == "192.168.1.50"
    assert "MiniUPnPd" in result[0]["server"]


def test_ssdp_discover_deduplicates_same_ip(monkeypatch):
    """Two responses from the same IP should only produce one entry."""
    response_data = b"HTTP/1.1 200 OK\r\nSERVER: TestDevice/1.0\r\n\r\n"
    calls = {"n": 0}

    class _MockSockDupIP:
        def setsockopt(self, *a): pass
        def settimeout(self, t): pass
        def sendto(self, data, addr): pass

        def recvfrom(self, size):
            if calls["n"] < 2:
                calls["n"] += 1
                return (response_data, ("192.168.1.50", 1900))
            raise socket.timeout()

        def close(self): pass

    monkeypatch.setattr(socket, "socket", lambda *a, **kw: _MockSockDupIP())
    result = _ssdp_discover(timeout=0.1)
    assert len(result) == 1


def test_ssdp_discover_empty_server_header(monkeypatch):
    """Response with no SERVER header should still produce an entry with empty server."""
    response_data = b"HTTP/1.1 200 OK\r\nUSN: uuid:xyz\r\n\r\n"
    calls = {"n": 0}

    class _MockSockNoServer:
        def setsockopt(self, *a): pass
        def settimeout(self, t): pass
        def sendto(self, data, addr): pass

        def recvfrom(self, size):
            if calls["n"] == 0:
                calls["n"] += 1
                return (response_data, ("10.0.0.5", 1900))
            raise socket.timeout()

        def close(self): pass

    monkeypatch.setattr(socket, "socket", lambda *a, **kw: _MockSockNoServer())
    result = _ssdp_discover(timeout=0.1)
    assert len(result) == 1
    assert result[0]["server"] == ""


# ── _open_ports ────────────────────────────────────────────────────────────────


def test_open_ports_all_refused(monkeypatch):
    def fake_create_connection(addr, timeout):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    result = _open_ports("192.168.1.1", ports=[22, 80, 443])
    assert result == []


def test_open_ports_os_error(monkeypatch):
    def fake_create_connection(addr, timeout):
        raise OSError("no route to host")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    result = _open_ports("192.168.1.1", ports=[22, 80])
    assert result == []


def test_open_ports_timeout(monkeypatch):
    def fake_create_connection(addr, timeout):
        raise socket.timeout("timed out")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    result = _open_ports("192.168.1.1", ports=[80])
    assert result == []


def test_open_ports_port_80_only_open(monkeypatch):
    """Create_connection succeeds only for port 80."""

    class _FakeConn:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_create_connection(addr, timeout):
        host, port = addr
        if port == 80:
            return _FakeConn()
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    result = _open_ports("192.168.1.1", ports=[22, 80, 443])
    assert result == [80]


def test_open_ports_multiple_open(monkeypatch):
    open_set = {22, 80}

    class _FakeConn:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_create_connection(addr, timeout):
        host, port = addr
        if port in open_set:
            return _FakeConn()
        raise ConnectionRefusedError()

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    result = _open_ports("192.168.1.1", ports=[22, 80, 443])
    assert set(result) == {22, 80}


def test_open_ports_empty_port_list(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda a, t: (_ for _ in ()).throw(OSError()))
    result = _open_ports("192.168.1.1", ports=[])
    assert result == []


# ── _check_default_creds ──────────────────────────────────────────────────────


class _FakeHTTPResp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_check_default_creds_all_fail(monkeypatch):
    def fake_urlopen(req, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert _check_default_creds("192.168.1.1", 80) is None


def test_check_default_creds_first_pair_succeeds(monkeypatch):
    """First credential pair (admin/admin) gets a 200 — should return that pair."""
    call_count = {"n": 0}

    def fake_urlopen(req, timeout):
        call_count["n"] += 1
        return _FakeHTTPResp(200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = _check_default_creds("192.168.1.1", 80)
    assert result == ("admin", "admin")
    # Should short-circuit after the first successful response
    assert call_count["n"] == 1


def test_check_default_creds_later_pair_succeeds(monkeypatch):
    """First two pairs fail, third succeeds — returns the successful pair."""
    call_count = {"n": 0}

    def fake_urlopen(req, timeout):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise OSError("rejected")
        return _FakeHTTPResp(200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = _check_default_creds("192.168.1.1", 80)
    assert result is not None
    user, pwd = result
    assert isinstance(user, str)
    assert isinstance(pwd, str)


def test_check_default_creds_non_200_response(monkeypatch):
    """401 responses should not count as success."""
    def fake_urlopen(req, timeout):
        raise Exception("HTTP 401")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert _check_default_creds("192.168.1.1", 80) is None


def test_check_default_creds_uses_basic_auth_header(monkeypatch):
    """Verify that the Authorization header is set in each request."""
    seen_headers = []

    def fake_urlopen(req, timeout):
        seen_headers.append(req.get_header("Authorization"))
        raise OSError("refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    _check_default_creds("192.168.1.1", 80)
    assert all(h.startswith("Basic ") for h in seen_headers)
    assert len(seen_headers) > 0


# ── _tls_expiry_days ──────────────────────────────────────────────────────────


def test_tls_expiry_days_connection_error(monkeypatch):
    def fake_create_connection(addr, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    result = _tls_expiry_days("192.168.1.1", 443)
    assert result is None


def test_tls_expiry_days_ssl_error(monkeypatch):
    class _FakeRaw:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_create_connection(addr, timeout):
        return _FakeRaw()

    import ssl
    def fake_wrap_socket(raw, server_hostname):
        raise ssl.SSLError("handshake failed")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    # Patch the ssl context's wrap_socket via the module-level ssl
    import errex.scanners.network as net_mod
    original_create_default_context = ssl.create_default_context

    class _FakeCtx:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def wrap_socket(self, raw, server_hostname):
            raise ssl.SSLError("ssl error")

    monkeypatch.setattr(ssl, "create_default_context", lambda: _FakeCtx())
    result = _tls_expiry_days("192.168.1.1", 443)
    assert result is None


def test_tls_expiry_days_returns_none_on_any_exception(monkeypatch):
    """Any unexpected exception during TLS check should return None."""
    def fake_create_connection(addr, timeout):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    result = _tls_expiry_days("192.168.1.1", 443)
    assert result is None


# ── _mqtt_unauthenticated ─────────────────────────────────────────────────────
# paho is not installed on the test runner; these tests exercise the raw-socket
# fallback path via the ImportError branch.


def test_mqtt_unauthenticated_port_closed(monkeypatch):
    """Raw socket connection fails → port closed → False."""
    # Ensure paho import fails so we hit the fallback
    import sys
    monkeypatch.setitem(sys.modules, "paho", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", None)

    def fake_create_connection(addr, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    assert _mqtt_unauthenticated("192.168.1.1") is False


def test_mqtt_unauthenticated_port_open(monkeypatch):
    """Raw socket connection succeeds → port open → True (fallback path)."""
    import sys
    monkeypatch.setitem(sys.modules, "paho", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", None)

    class _FakeConn:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_create_connection(addr, timeout):
        return _FakeConn()

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    assert _mqtt_unauthenticated("192.168.1.1") is True


def test_mqtt_unauthenticated_raw_socket_connection_refused(monkeypatch):
    """ConnectionRefusedError is a subclass of OSError — should return False."""
    import sys
    monkeypatch.setitem(sys.modules, "paho", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt", None)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", None)

    def fake_create_connection(addr, timeout):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    assert _mqtt_unauthenticated("192.168.1.1") is False


# ── get_findings ──────────────────────────────────────────────────────────────


def _patch_discovery_empty(monkeypatch):
    """Patch all three discovery functions to return empty lists."""
    monkeypatch.setattr("errex.scanners.network._arp_table", lambda: [])
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])


def test_get_findings_no_devices_returns_empty(monkeypatch):
    _patch_discovery_empty(monkeypatch)
    findings = get_findings()
    assert findings == []


def test_get_findings_returns_network_devices_found_finding(monkeypatch):
    """When devices are found, a summary 'network-devices-found' Finding is emitted."""
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.100", "hostname": "router", "mac": "aa:bb:cc:00:00:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    # No open ports so security findings are minimal
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [])

    findings = get_findings()
    ids = [f.id for f in findings]
    assert "network-devices-found" in ids


def test_get_findings_network_devices_found_severity_info(monkeypatch):
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.100", "hostname": "router", "mac": "aa:bb:cc:00:00:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [])

    findings = get_findings()
    summary = next(f for f in findings if f.id == "network-devices-found")
    assert summary.severity == "info"
    assert summary.platform == "network"


def test_get_findings_device_count_in_title(monkeypatch):
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [
            {"ip": "192.168.1.1", "hostname": "a", "mac": "aa:bb:cc:00:00:01"},
            {"ip": "192.168.1.2", "hostname": "b", "mac": "aa:bb:cc:00:00:02"},
        ],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [])

    findings = get_findings()
    summary = next(f for f in findings if f.id == "network-devices-found")
    assert "2" in summary.title


def test_get_findings_telnet_open_produces_critical_finding(monkeypatch):
    """Port 23 open on a device → a critical telnet finding."""
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.100", "hostname": "router", "mac": "aa:bb:cc:00:00:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [23])

    findings = get_findings()
    telnet_findings = [f for f in findings if "telnet" in f.id]
    assert len(telnet_findings) == 1
    assert telnet_findings[0].severity == "critical"
    assert "192.168.1.100" in telnet_findings[0].title or "192.168.1.100" in telnet_findings[0].detail


def test_get_findings_telnet_finding_id_contains_ip(monkeypatch):
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.100", "hostname": "router", "mac": "aa:bb:cc:00:00:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [23])

    findings = get_findings()
    telnet = next(f for f in findings if "telnet" in f.id)
    # ID should encode the IP (dots replaced with underscores)
    assert "192_168_1_100" in telnet.id


def test_get_findings_no_open_ports_no_security_findings(monkeypatch):
    """A device with no open ports should produce only the summary finding."""
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.100", "hostname": "router", "mac": "aa:bb:cc:00:00:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [])

    findings = get_findings()
    security_findings = [f for f in findings if f.id != "network-devices-found"]
    # Offline-device check may add findings; filter by category
    net_security = [f for f in security_findings if "telnet" in f.id or "mqtt" in f.id or "creds" in f.id or "cert" in f.id]
    assert net_security == []


def test_get_findings_ssdp_only_device(monkeypatch):
    """Devices discovered only via SSDP (not ARP) should also be checked."""
    monkeypatch.setattr("errex.scanners.network._arp_table", lambda: [])
    monkeypatch.setattr(
        "errex.scanners.network._ssdp_discover",
        lambda *a, **kw: [{"ip": "192.168.1.50", "server": "UPnP/1.0"}],
    )
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [])

    findings = get_findings()
    summary = next(f for f in findings if f.id == "network-devices-found")
    assert "192.168.1.50" in summary.detail


def test_get_findings_mqtt_open_unauthenticated_produces_high_finding(monkeypatch):
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.200", "hostname": "broker", "mac": "de:ad:be:ef:00:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [1883])
    monkeypatch.setattr("errex.scanners.network._mqtt_unauthenticated", lambda ip: True)

    findings = get_findings()
    mqtt_findings = [f for f in findings if "mqtt" in f.id]
    assert len(mqtt_findings) == 1
    assert mqtt_findings[0].severity == "high"


def test_get_findings_mqtt_port_open_but_authenticated(monkeypatch):
    """Port 1883 open but broker requires auth → no mqtt finding."""
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.200", "hostname": "broker", "mac": "de:ad:be:ef:00:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [1883])
    monkeypatch.setattr("errex.scanners.network._mqtt_unauthenticated", lambda ip: False)

    findings = get_findings()
    mqtt_findings = [f for f in findings if "mqtt" in f.id]
    assert mqtt_findings == []


def test_get_findings_default_creds_produces_critical_finding(monkeypatch):
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.1", "hostname": "cam", "mac": "aa:bb:cc:00:00:ff"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [80])
    monkeypatch.setattr(
        "errex.scanners.network._check_default_creds",
        lambda ip, port: ("admin", "admin"),
    )

    findings = get_findings()
    cred_findings = [f for f in findings if "creds" in f.id]
    assert len(cred_findings) == 1
    assert cred_findings[0].severity == "critical"
    assert "admin" in cred_findings[0].detail


def test_get_findings_skips_loopback(monkeypatch):
    """127.x.x.x addresses should be skipped during security checks."""
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "127.0.0.1", "hostname": "localhost", "mac": ""}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])

    open_ports_called = {"called": False}

    def fake_open_ports(ip, *a, **kw):
        open_ports_called["called"] = True
        return []

    monkeypatch.setattr("errex.scanners.network._open_ports", fake_open_ports)

    get_findings()
    assert not open_ports_called["called"]


def test_get_findings_mdns_device_included(monkeypatch):
    """Devices discovered via mDNS (when zeroconf is installed) are included."""
    monkeypatch.setattr("errex.scanners.network._arp_table", lambda: [])
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr(
        "errex.scanners.network._mdns_discover",
        lambda *a, **kw: [{"ip": "192.168.1.77", "name": "hue-bridge", "port": 80, "type": "_hue._tcp.local."}],
    )
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [])

    findings = get_findings()
    summary = next(f for f in findings if f.id == "network-devices-found")
    assert "192.168.1.77" in summary.detail


def test_get_findings_tls_cert_expiring_soon_produces_finding(monkeypatch):
    """TLS cert expiring in <30 days → cert-expiry finding."""
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.10", "hostname": "nas", "mac": "aa:bb:cc:00:ff:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [443])
    monkeypatch.setattr("errex.scanners.network._tls_expiry_days", lambda ip, port: 5)

    findings = get_findings()
    cert_findings = [f for f in findings if "cert" in f.id]
    assert len(cert_findings) == 1
    assert cert_findings[0].severity == "high"  # <7 days → high


def test_get_findings_tls_cert_not_expiring_soon(monkeypatch):
    """TLS cert expiring in >30 days → no cert-expiry finding."""
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.10", "hostname": "nas", "mac": "aa:bb:cc:00:ff:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [443])
    monkeypatch.setattr("errex.scanners.network._tls_expiry_days", lambda ip, port: 90)

    findings = get_findings()
    cert_findings = [f for f in findings if "cert" in f.id]
    assert cert_findings == []


def test_get_findings_returns_list_of_findings(monkeypatch):
    """get_findings return type is always a list (possibly empty)."""
    _patch_discovery_empty(monkeypatch)
    result = get_findings()
    assert isinstance(result, list)


def test_get_findings_finding_ids_are_strings(monkeypatch):
    monkeypatch.setattr(
        "errex.scanners.network._arp_table",
        lambda: [{"ip": "192.168.1.1", "hostname": "x", "mac": "00:00:00:00:00:01"}],
    )
    monkeypatch.setattr("errex.scanners.network._ssdp_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._mdns_discover", lambda *a, **kw: [])
    monkeypatch.setattr("errex.scanners.network._open_ports", lambda ip, *a, **kw: [])

    findings = get_findings()
    for f in findings:
        assert isinstance(f.id, str)
        assert isinstance(f.severity, str)
        assert isinstance(f.title, str)
