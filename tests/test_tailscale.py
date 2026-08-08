"""Tailscale soft probe - no live Tailscale required.

    python tests/test_tailscale.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import tailscale as ts

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def run():
    ts._reset_cache()

    # ---- peer_for_path ----
    check("UNC host from backslash path",
          ts.peer_for_path(r"\\nas\50tb\OBS") == "nas")
    check("UNC host from forward-slash path",
          ts.peer_for_path("//100.84.207.58/50tb/OBS") == "100.84.207.58")
    check("drive letter has no peer",
          ts.peer_for_path("Z:/OBS Recordings") is None)
    check("blank root has no peer",
          ts.peer_for_path("") is None)
    check("extended UNC",
          ts.peer_for_path(r"\\?\UNC\nas.tail25e601.ts.net\share") == "nas.tail25e601.ts.net")

    # ---- _parse_status ----
    raw = {
        "BackendState": "Running",
        "Self": {"Online": True},
        "Peer": {
            "key1": {
                "HostName": "nas",
                "DNSName": "nas.tail25e601.ts.net.",
                "Online": True,
                "TailscaleIPs": ["100.84.207.58"],
            },
            "key2": {
                "HostName": "laptop",
                "Online": False,
                "TailscaleIPs": ["100.78.124.64"],
            },
        },
    }
    parsed = ts._parse_status(raw)
    check("parse: backend", parsed["backend"] == "Running")
    check("parse: self online", parsed["self_online"] is True)
    check("parse: peer by hostname", parsed["peers"].get("nas") is True)
    check("parse: peer by MagicDNS",
          parsed["peers"].get("nas.tail25e601.ts.net") is True)
    check("parse: peer by IP", parsed["peers"].get("100.84.207.58") is True)
    check("parse: offline peer", parsed["peers"].get("laptop") is False)
    check("parse: None raw", ts._parse_status(None) is None)
    check("parse: junk raw", ts._parse_status("nope") is None)

    rich = {
        "BackendState": "Running",
        "Version": "1.102.2-t6cac91817-g6ff0ddc72",
        "MagicDNSSuffix": "tail25e601.ts.net",
        "CurrentTailnet": {"Name": "user@example.com"},
        "Self": {
            "HostName": "Alien-Pc",
            "DNSName": "alien-pc.tail25e601.ts.net.",
            "Online": True,
            "OS": "windows",
            "TailscaleIPs": ["100.90.134.9", "fd7a:115c:a1e0::b33:860a"],
        },
        "Peer": {
            "key1": {
                "HostName": "nas",
                "DNSName": "nas.tail25e601.ts.net.",
                "Online": True,
                "Active": True,
                "Relay": "lhr",
                "OS": "linux",
                "CurAddr": "192.168.68.59:41641",
                "TailscaleIPs": ["100.84.207.58"],
                "RxBytes": 100,
                "TxBytes": 200,
            },
            "key2": {
                "HostName": "laptop",
                "DNSName": "strix-laptop.tail25e601.ts.net.",
                "Online": False,
                "Active": False,
                "Relay": "lhr",
                "OS": "windows",
                "LastSeen": "2026-08-06T08:01:19.1Z",
                "TailscaleIPs": ["100.108.233.43"],
            },
        },
    }
    r = ts._parse_status(rich)
    check("rich: version short", r["version_short"] == "1.102.2", r.get("version_short"))
    check("rich: magic dns", r["magic_dns"] == "tail25e601.ts.net")
    check("rich: self hostname", r["self"]["hostname"] == "Alien-Pc")
    check("rich: self ipv4 only", r["self"]["ips"] == ["100.90.134.9"], r["self"]["ips"])
    check("rich: peer count", r["peer_count"] == 2)
    check("rich: online peers", r["online_peers"] == 1)
    check("rich: peer_list order online first",
          r["peer_list"][0]["hostname"] == "nas")
    check("rich: nas active+direct",
          r["peer_list"][0]["active"] and r["peer_list"][0]["direct"])
    check("rich: offline last_seen kept",
          "last_seen" in r["peer_list"][1], r["peer_list"][1])
    check("rich: peers map still works",
          r["peers"].get("nas") is True and r["peers"].get("laptop") is False)

    phone = ts._parse_status({
        "BackendState": "Running",
        "Self": {"Online": True},
        "Peer": {
            "p": {
                "HostName": "localhost",
                "DNSName": "iphone-12-pro.tail25e601.ts.net.",
                "Online": False,
                "TailscaleIPs": ["100.94.111.24"],
                "OS": "iOS",
                "LastSeen": "2026-07-30T12:58:11.1Z",
            },
        },
    })
    check("rich: localhost HostName → MagicDNS label",
          phone["peer_list"][0]["hostname"] == "iphone-12-pro",
          phone["peer_list"][0])


    # ---- diagnose with mocked status / isdir ----
    work = tempfile.mkdtemp(prefix="nebula-ts-test-")
    real_root = os.path.join(work, "nas")
    os.makedirs(real_root)
    missing = os.path.join(work, "missing")

    real_status = ts.status
    real_available = ts.available

    def with_status(payload, avail=True):
        def fake_status(force=False):
            return payload
        def fake_available():
            return avail
        ts.status = fake_status
        ts.available = fake_available

    try:
        with_status({
            "backend": "Running",
            "self_online": True,
            "peers": {"nas": True, "100.84.207.58": True},
        })
        check("diagnose: blank is off", ts.diagnose("") == "off")
        check("diagnose: reachable + TS up",
              ts.diagnose(real_root) == "nas_up")
        check("diagnose label: Tailscale up",
              ts.diagnose_label("nas_up") == "Tailscale up")

        with_status(None, avail=False)
        check("diagnose: reachable without CLI",
              ts.diagnose(real_root) == "nas_reachable")
        check("diagnose: down, CLI missing",
              ts.diagnose(missing) == "nas_down_tailscale_missing")
        check("diagnose label: missing CLI silent",
              ts.diagnose_label("nas_down_tailscale_missing") == "")

        with_status(None, avail=True)
        check("diagnose: down, CLI present but status fail",
              ts.diagnose(missing) == "nas_down_tailscale_down")

        with_status({
            "backend": "Stopped",
            "self_online": False,
            "peers": {},
        })
        check("diagnose: Tailscale stopped",
              ts.diagnose(missing) == "nas_down_tailscale_down")
        check("diagnose label: Tailscale down",
              ts.diagnose_label("nas_down_tailscale_down") == "Tailscale down")

        with_status({
            "backend": "Running",
            "self_online": True,
            "peers": {"nas": False},
        })
        check("diagnose: peer offline",
              ts.diagnose(r"\\nas\share") == "nas_down_peer_offline")
        check("diagnose label: peer offline",
              ts.diagnose_label("nas_down_peer_offline") == "Tailscale peer offline")

        with_status({
            "backend": "Running",
            "self_online": True,
            "peers": {"nas": True},
        })
        check("diagnose: path down but TS fine",
              ts.diagnose(missing) == "nas_down")
        check("diagnose: drive letter down, no peer check",
              ts.diagnose("Z:/nope") == "nas_down")
    finally:
        ts.status = real_status
        ts.available = real_available
        ts._reset_cache()

    # ---- home_lan_preferred / endpoint heuristics ----
    check("endpoint: private LAN",
          ts._endpoint_looks_lan("192.168.68.59:41641") is True)
    check("endpoint: public remote",
          ts._endpoint_looks_lan("88.97.207.10:7578") is False)
    check("endpoint: empty", ts._endpoint_looks_lan("") is False)
    check("endpoint: ipv6 tailnet ignored",
          ts._endpoint_looks_lan("[fd7a:115c:a1e0::1]:41641") is False)

    real_cur = ts.peer_cur_addr
    real_ping = ts.ping_rtt_ms
    try:
        ts.peer_cur_addr = lambda host, st=None: "192.168.68.59:1"
        check("home: CurAddr private + isdir",
              ts.home_lan_preferred(real_root) is True)
        ts.peer_cur_addr = lambda host, st=None: "82.11.1.1:1"
        check("home: CurAddr public rejects",
              ts.home_lan_preferred(real_root) is False)
        ts.peer_cur_addr = lambda host, st=None: None
        ts.ping_rtt_ms = lambda host, count=1: 4.0
        check("home: RTT fallback same-site",
              ts.home_lan_preferred(real_root) is True)
        ts.ping_rtt_ms = lambda host, count=1: 29.0
        check("home: RTT fallback cross-site",
              ts.home_lan_preferred(real_root) is False)
        check("home: missing lan root",
              ts.home_lan_preferred(missing) is False)
    finally:
        ts.peer_cur_addr = real_cur
        ts.ping_rtt_ms = real_ping
        ts._reset_cache()

    # ---- available() with which monkeypatch ----
    import shutil
    real_which = shutil.which
    try:
        shutil.which = lambda name: None
        ts._reset_cache()
        check("available: missing CLI", ts.available() is False)
        shutil.which = lambda name: r"C:\fake\tailscale.exe"
        ts._reset_cache()
        check("available: CLI on PATH", ts.available() is True)
    finally:
        shutil.which = real_which
        ts._reset_cache()

    # ---- status() soft-fail when subprocess fails ----
    real_run = ts._run_status_json
    try:
        ts._reset_cache()
        shutil.which = lambda name: r"C:\fake\tailscale.exe"
        ts._which_cache = r"C:\fake\tailscale.exe"
        ts._run_status_json = lambda: None
        check("status: soft fail", ts.status(force=True) is None)

        fixture = {
            "BackendState": "Running",
            "Self": {"Online": True},
            "Peer": {},
        }
        ts._run_status_json = lambda: fixture
        ts._reset_cache()
        ts._which_cache = r"C:\fake\tailscale.exe"
        got = ts.status(force=True)
        check("status: parses fixture",
              got is not None and got["backend"] == "Running", got)
    finally:
        ts._run_status_json = real_run
        shutil.which = real_which
        ts._reset_cache()


run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
