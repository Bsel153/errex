"""Network/IoT scanner — discovers LAN devices and runs security checks.

Optional dependencies (installed with pip install errex[scan]):
  zeroconf   — mDNS/Bonjour device discovery
  paho-mqtt  — MQTT broker authentication check

All optional imports are guarded so errex still works without them.
"""
from __future__ import annotations

import base64
import datetime
import re
import socket
import ssl
import subprocess
import time
import urllib.request
from ._base import Finding

_DEFAULT_CREDS = [
    ("admin", "admin"),
    ("admin", "password"),
    ("admin", "1234"),
    ("admin", ""),
    ("root", "root"),
    ("admin", "123456"),
]
_SCAN_PORTS = [22, 23, 80, 443, 1883, 8080, 8443, 8883]


# ── Device discovery ────────────────────────────────────────────────────────


def _arp_table() -> list[dict]:
    """Read current ARP table: [{ip, mac, hostname}]."""
    try:
        r = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
        devices = []
        for line in r.stdout.splitlines():
            m = re.match(r'(\S+)\s+\(([0-9.]+)\)\s+at\s+([0-9a-fA-F:]+)', line)
            if m:
                devices.append({
                    "hostname": m.group(1),
                    "ip": m.group(2),
                    "mac": m.group(3).lower(),
                })
        return devices
    except Exception:
        return []


def _ssdp_discover(timeout: float = 3.0) -> list[dict]:
    """Discover UPnP devices via SSDP M-SEARCH (no dependencies)."""
    msg = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 3\r\n"
        "ST: upnp:rootdevice\r\n\r\n"
    ).encode()
    devices: list[dict] = []
    seen: set[str] = set()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.sendto(msg, ("239.255.255.250", 1900))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(65507)
                ip = addr[0]
                if ip in seen:
                    continue
                seen.add(ip)
                text = data.decode(errors="replace")
                server = re.search(r"SERVER:\s*(.+)", text, re.IGNORECASE)
                devices.append({
                    "ip": ip,
                    "server": server.group(1).strip() if server else "",
                })
            except socket.timeout:
                break
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return devices


def _mdns_discover(timeout: float = 4.0) -> list[dict]:
    """Discover mDNS/Bonjour services. Requires zeroconf."""
    try:
        from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
    except ImportError:
        return []

    devices: list[dict] = []
    zc = Zeroconf()

    def _on(zc_inst, service_type, name, state_change):
        if state_change is not ServiceStateChange.Added:
            return
        try:
            info = zc_inst.get_service_info(service_type, name)
            if info and info.addresses:
                devices.append({
                    "name": name.split(".")[0],
                    "ip": socket.inet_ntoa(info.addresses[0]),
                    "port": info.port,
                    "type": service_type,
                })
        except Exception:
            pass

    types = [
        "_homekit._tcp.local.",
        "_hue._tcp.local.",
        "_googlecast._tcp.local.",
        "_http._tcp.local.",
    ]
    [ServiceBrowser(zc, t, handlers=[_on]) for t in types]
    time.sleep(timeout)
    zc.close()
    return devices


# ── Per-device checks ────────────────────────────────────────────────────────


def _open_ports(ip: str, ports: list[int] = _SCAN_PORTS, timeout: float = 0.8) -> list[int]:
    open_p = []
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                open_p.append(port)
        except (ConnectionRefusedError, OSError, socket.timeout):
            pass
    return open_p


def _check_default_creds(ip: str, port: int) -> tuple[str, str] | None:
    for user, pwd in _DEFAULT_CREDS:
        token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
        req = urllib.request.Request(
            f"http://{ip}:{port}/",
            headers={"Authorization": f"Basic {token}", "User-Agent": "errex/0.21.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return (user, pwd)
        except Exception:
            pass
    return None


def _tls_expiry_days(ip: str, port: int) -> int | None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((ip, port), timeout=5) as raw:
            with ctx.wrap_socket(raw, server_hostname=ip) as ssock:
                cert = ssock.getpeercert()
                not_after = cert.get("notAfter", "")
                if not_after:
                    expiry = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                    return (expiry - datetime.datetime.utcnow()).days
    except Exception:
        return None


def _mqtt_unauthenticated(ip: str) -> bool:
    """Return True if MQTT broker on port 1883 accepts connections without credentials."""
    try:
        import paho.mqtt.client as mqtt  # type: ignore
        result = {"ok": False}

        def on_connect(client, userdata, flags, rc):
            result["ok"] = rc == 0
            client.disconnect()

        client = mqtt.Client()
        client.on_connect = on_connect
        client.connect_async(ip, 1883, 5)
        client.loop_start()
        time.sleep(2)
        client.loop_stop()
        return result["ok"]
    except ImportError:
        # paho not installed — fall back to raw socket check
        try:
            with socket.create_connection((ip, 1883), timeout=3):
                return True  # port open, likely MQTT
        except Exception:
            return False
    except Exception:
        return False


# ── Main entry point ─────────────────────────────────────────────────────────


def get_findings() -> list[Finding]:
    """Discover and scan devices on the local network. Returns all findings."""
    findings: list[Finding] = []

    # Collect devices from all discovery methods
    arp = _arp_table()
    ssdp = _ssdp_discover()
    mdns = _mdns_discover()

    devices: dict[str, dict] = {}
    for d in arp:
        ip = d["ip"]
        devices.setdefault(ip, {"ip": ip, "hostname": d.get("hostname", ""), "mac": d.get("mac", "")})

    for d in ssdp:
        ip = d["ip"]
        devices.setdefault(ip, {"ip": ip, "hostname": "", "mac": ""})
        devices[ip]["server"] = d.get("server", "")

    for d in mdns:
        ip = d.get("ip", "")
        if not ip:
            continue
        devices.setdefault(ip, {"ip": ip, "hostname": d.get("name", ""), "mac": ""})

    if not devices:
        return []

    device_list = sorted(devices.values(), key=lambda x: x["ip"])

    # Offline-device detection (compares against history of previous scans)
    try:
        from .diagnostics import check_offline_devices
        findings.extend(check_offline_devices(device_list))
    except Exception:
        pass

    # Summary info finding
    lines = [
        f"  {d['ip']:16s} {d.get('hostname',''):22s} {d.get('server','') or d.get('mac','')}"
        for d in device_list
    ]
    findings.append(Finding(
        id="network-devices-found",
        severity="info",
        category="security",
        platform="network",
        title=f"{len(device_list)} device(s) on local network",
        detail="\n".join(lines),
    ))

    # Per-device security checks (cap at 20)
    for device in device_list[:20]:
        ip = device["ip"]
        if ip.startswith("127.") or ip == "::1":
            continue

        open_p = _open_ports(ip)
        tag = ip.replace(".", "_")

        # Telnet (critical)
        if 23 in open_p:
            findings.append(Finding(
                id=f"network-telnet-{tag}",
                severity="critical",
                category="security",
                platform="network",
                title=f"Telnet exposed on {ip}",
                detail=f"Device at {ip} has Telnet (port 23) open. All data including passwords is transmitted in cleartext.",
                fix_cmd=f"# Log into {ip} and disable Telnet in the device admin panel.",
            ))

        # Unauthenticated MQTT
        if 1883 in open_p and _mqtt_unauthenticated(ip):
            findings.append(Finding(
                id=f"network-mqtt-open-{tag}",
                severity="high",
                category="security",
                platform="network",
                title=f"MQTT broker at {ip} accepts unauthenticated connections",
                detail=f"Anyone on the network can subscribe/publish to any topic on this broker without a password.",
                fix_cmd=f"# Configure the MQTT broker at {ip} to require authentication.",
            ))

        # Default credentials on HTTP
        for http_port in (80, 8080):
            if http_port in open_p:
                creds = _check_default_creds(ip, http_port)
                if creds:
                    findings.append(Finding(
                        id=f"network-default-creds-{tag}",
                        severity="critical",
                        category="security",
                        platform="network",
                        title=f"Default credentials work on {ip}:{http_port}",
                        detail=f"Username '{creds[0]}' / password '{creds[1]}' grants access to http://{ip}:{http_port}. Change the password immediately.",
                        fix_cmd=f"# Log into http://{ip}:{http_port} and change the admin password.",
                    ))
                break  # only check once per device

        # TLS cert expiry
        for tls_port in (443, 8443):
            if tls_port in open_p:
                days = _tls_expiry_days(ip, tls_port)
                if days is not None and days < 30:
                    severity = "high" if days < 7 else "medium"
                    findings.append(Finding(
                        id=f"network-cert-expiry-{tag}",
                        severity=severity,
                        category="misconfiguration",
                        platform="network",
                        title=f"TLS certificate on {ip}:{tls_port} expires in {days} day(s)",
                        detail=f"The TLS certificate will expire in {days} days. Renew it to avoid connection errors.",
                    ))
                break

    return findings
