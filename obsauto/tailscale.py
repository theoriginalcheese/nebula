"""Soft Tailscale probe - optional, like ffmpeg in thumbs.py.

Used to *explain* why NAS offload is waiting and to wake the offloader when
the tailnet comes back. Never a delete authority: the offloader still gates
on ``os.path.isdir(nas_offload_root)`` and byte-verified copies only.

No new dependencies. Missing CLI / timeout / bad JSON → degrade quietly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from .silent_proc import run_kwargs
from .fsprobe import isdir_within

_STATUS_TTL = 15.0  # snapshot polls often while awake; don't re-shell every beat
_TIMEOUT = 3

# Cached which() + last status snapshot.
_which_cache = None
_status_cache = (0.0, None)  # (monotonic, parsed dict or None)


def _reset_cache():
    """Test hook - drop which/status caches between cases."""
    global _which_cache, _status_cache
    _which_cache = None
    _status_cache = (0.0, None)


def available():
    """Is the Tailscale CLI on PATH?"""
    global _which_cache
    if _which_cache is None:
        _which_cache = shutil.which("tailscale") or False
    return bool(_which_cache)


def peer_for_path(root):
    """UNC host from a NAS root, or None for drive letters / local paths.

    ``\\\\nas\\share\\OBS`` → ``nas``
    ``\\\\100.84.207.58\\50tb\\OBS`` → ``100.84.207.58``
    ``Z:/OBS Recordings`` → None
    """
    if not root:
        return None
    text = root.strip().replace("/", "\\")
    if not text.startswith("\\\\"):
        return None
    # \\host\share\...  or  \\?\UNC\host\share\...
    body = text[2:]
    if body.upper().startswith("?\\UNC\\"):
        body = body[6:]
    host, _, _rest = body.partition("\\")
    host = host.strip().rstrip(".")
    return host or None


def _run_status_json():
    exe = shutil.which("tailscale") if _which_cache is None else _which_cache
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "status", "--json"],
            capture_output=True,
            timeout=_TIMEOUT,
            check=False,
            **run_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if not result or result.returncode != 0 or not result.stdout:
        return None
    try:
        return json.loads(result.stdout.decode("utf-8", errors="replace"))
    except (ValueError, TypeError):
        return None


def _ipv4s(ips):
    """Prefer displayable IPv4 from TailscaleIPs; keep order, drop blanks."""
    out = []
    for ip in ips or []:
        if not ip or ":" in str(ip):
            continue
        out.append(str(ip))
    return out


def _peer_entry(peer):
    """One peer for the Remote pane — only fields the CLI actually gave."""
    if not isinstance(peer, dict):
        return None
    hostname = (peer.get("HostName") or "").strip()
    dns = (peer.get("DNSName") or "").rstrip(".")
    dns_short = dns.split(".", 1)[0] if dns else ""
    # Some clients report HostName as "localhost" — MagicDNS label is honest.
    if (not hostname) or hostname.lower() in ("localhost", "local"):
        hostname = dns_short or hostname
    ips = _ipv4s(peer.get("TailscaleIPs"))
    if not hostname and not dns and not ips:
        return None
    online = bool(peer.get("Online"))
    active = bool(peer.get("Active"))
    entry = {
        "hostname": hostname or dns_short or (ips[0] if ips else ""),
        "dns": dns,
        "online": online,
        "active": active,
        "ips": ips,
        "os": (peer.get("OS") or "").strip(),
        "relay": (peer.get("Relay") or "").strip(),
        "direct": bool(peer.get("CurAddr")),
    }
    # LastSeen is only meaningful when offline (zero-time means "never / n/a").
    last = peer.get("LastSeen") or ""
    if (not online) and last and not str(last).startswith("0001-01-01"):
        entry["last_seen"] = str(last)
    rx = peer.get("RxBytes")
    tx = peer.get("TxBytes")
    if isinstance(rx, int) and rx > 0:
        entry["rx_bytes"] = rx
    if isinstance(tx, int) and tx > 0:
        entry["tx_bytes"] = tx
    return entry


def _parse_status(raw):
    """Shrink the CLI JSON to what Nebula needs. ``raw`` may be None."""
    if not isinstance(raw, dict):
        return None
    backend = raw.get("BackendState") or raw.get("Backend") or ""
    self_info = raw.get("Self") or {}
    self_online = bool(self_info.get("Online", backend == "Running"))
    peers = {}
    peer_list = []
    for peer in (raw.get("Peer") or {}).values():
        if not isinstance(peer, dict):
            continue
        online = bool(peer.get("Online"))
        # DNSName is usually "nas.tail….ts.net."; HostName is the short name.
        names = []
        for key in ("DNSName", "HostName"):
            val = (peer.get(key) or "").rstrip(".")
            if val:
                names.append(val)
                # Also the first label of a MagicDNS name.
                short = val.split(".", 1)[0]
                if short and short not in names:
                    names.append(short)
        for ip in peer.get("TailscaleIPs") or []:
            if ip:
                names.append(ip)
        for name in names:
            peers[name.lower()] = online
        entry = _peer_entry(peer)
        if entry:
            peer_list.append(entry)
    # Online + active first, then hostname — stable for the UI list.
    peer_list.sort(key=lambda p: (
        0 if p["online"] else 1,
        0 if p["active"] else 1,
        (p["hostname"] or "").lower(),
    ))
    self_dns = (self_info.get("DNSName") or "").rstrip(".")
    self_host = (self_info.get("HostName") or "").strip()
    tn = raw.get("CurrentTailnet") or {}
    magic = (raw.get("MagicDNSSuffix") or "").strip().rstrip(".")
    version = (raw.get("Version") or "").strip()
    # CLI versions look like "1.102.2-t6cac9…" — keep the numeric prefix for UI.
    version_short = version.split("-", 1)[0] if version else ""
    return {
        "backend": backend,
        "self_online": self_online,
        "peers": peers,
        "version": version,
        "version_short": version_short,
        "magic_dns": magic,
        "tailnet": (tn.get("Name") or "").strip(),
        "self": {
            "hostname": self_host,
            "dns": self_dns,
            "ips": _ipv4s(self_info.get("TailscaleIPs")),
            "os": (self_info.get("OS") or "").strip(),
            "online": self_online,
        },
        "peer_list": peer_list,
        "online_peers": sum(1 for p in peer_list if p["online"]),
        "peer_count": len(peer_list),
    }


def status(force=False):
    """Cached Tailscale status, or None if the CLI isn't usable.

    Returns at least ``{"backend", "self_online", "peers"}`` where ``peers``
    maps lowercase hostname/IP → online bool. When the CLI JSON is rich
    enough, also ``version``, ``magic_dns``, ``self``, ``peer_list``, counts.
    """
    global _status_cache, _which_cache
    if not available():
        return None
    now = time.monotonic()
    cached_at, cached = _status_cache
    if not force and cached is not None and (now - cached_at) < _STATUS_TTL:
        return cached
    if not force and cached is None and (now - cached_at) < _STATUS_TTL:
        # Recent miss - don't hammer a missing daemon every Settings paint.
        return None
    parsed = _parse_status(_run_status_json())
    _status_cache = (now, parsed)
    return parsed


def peer_online(host, st=None):
    """Is ``host`` (from a UNC path) online on the tailnet? None if unknown."""
    if not host:
        return None
    st = st if st is not None else status()
    if not st:
        return None
    return st["peers"].get(host.lower())


def peer_cur_addr(host, st=None):
    """Live WireGuard endpoint for ``host`` (e.g. ``192.168.68.59:41641``).

    Empty when the peer has no active path yet. Used to tell same-LAN
    (private CurAddr) from cross-site (public CurAddr) without trusting the
    overlapping Deco ``192.168.68.0/24`` at dad's house.
    """
    if not host:
        return None
    # Fresh CLI JSON — CurAddr isn't in the slim status() cache.
    payload = _run_status_json()
    if not isinstance(payload, dict):
        return None
    want = host.lower().strip().rstrip(".")
    want_short = want.split(".", 1)[0]
    for peer in (payload.get("Peer") or {}).values():
        if not isinstance(peer, dict):
            continue
        names = []
        for key in ("DNSName", "HostName"):
            val = (peer.get(key) or "").rstrip(".").lower()
            if val:
                names.append(val)
                names.append(val.split(".", 1)[0])
        for ip in peer.get("TailscaleIPs") or []:
            if ip:
                names.append(str(ip).lower())
        if want not in names and want_short not in names:
            continue
        cur = (peer.get("CurAddr") or "").strip()
        return cur or None
    return None


def _endpoint_looks_lan(cur_addr):
    """True when Tailscale's CurAddr is a private/site-local endpoint."""
    if not cur_addr:
        return False
    text = cur_addr.strip()
    # "[fd7a:…]:port" — Tailscale IPv6, not evidence of home LAN SMB.
    if text.startswith("["):
        return False
    host = text.rsplit(":", 1)[0]
    if host.startswith("192.168.") or host.startswith("10."):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".", 2)[1])
        except (ValueError, IndexError):
            return False
        return 16 <= second <= 31
    return False


# Same-site Tailscale ping is a few ms; mum↔dad was ~29ms in vault notes.
_HOME_RTT_MS = 12.0
_PING_TIMEOUT = 4


def ping_rtt_ms(host, count=1):
    """Best RTT in ms from ``tailscale ping``, or None on failure."""
    if not host or not available():
        return None
    exe = shutil.which("tailscale") if _which_cache is None else _which_cache
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "ping", "-c", str(max(1, int(count))), host],
            capture_output=True,
            timeout=_PING_TIMEOUT,
            check=False,
            **run_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if not result or not result.stdout:
        return None
    text = result.stdout.decode("utf-8", errors="replace")
    # "pong from nas (100.x) via 192.168.68.59:41641 in 2ms"
    best = None
    for line in text.splitlines():
        line = line.strip().lower()
        if " in " not in line or "ms" not in line:
            continue
        try:
            part = line.rsplit(" in ", 1)[1]
            num = part.replace("ms", "").strip().split()[0]
            val = float(num)
        except (IndexError, ValueError):
            continue
        if best is None or val < best:
            best = val
    return best


def home_lan_preferred(lan_root, peer="nas"):
    """Should offload use the LAN UNC instead of the Tailscale one?

    Cheap and conservative:
      1. ``lan_root`` must already be reachable (``isdir``).
      2. Prefer Tailscale ``CurAddr`` — private endpoint ⇒ same site.
         Public endpoint ⇒ remote site (dad's Virgin → mum's NAS).
      3. If no CurAddr yet, fall back to ping RTT ≤ ``_HOME_RTT_MS``.

    Never invents "home" from overlapping Deco subnets alone.
    """
    lan_root = (lan_root or "").strip()
    if not lan_root or not isdir_within(lan_root):
        return False
    cur = peer_cur_addr(peer)
    if cur:
        return _endpoint_looks_lan(cur)
    rtt = ping_rtt_ms(peer)
    if rtt is None:
        return False
    return rtt <= _HOME_RTT_MS


def diagnose(root):
    """Honest short code for UI/logs. Never invents a healthy NAS.

    Codes:
      nas_up                      path reachable; Tailscale online (optional clause)
      nas_reachable               path reachable; Tailscale unknown/absent
      nas_down                    path down; Tailscale up (or no peer to check)
      nas_down_tailscale_down     path down; backend offline / status failed
      nas_down_peer_offline       path down; UNC peer listed offline
      nas_down_tailscale_missing  path down; CLI not on PATH
      off                         blank root
    """
    root = (root or "").strip()
    if not root:
        return "off"
    up = os.path.isdir(root)
    st = status()

    if up:
        if st and st["self_online"] and (
                not st["backend"] or st["backend"] == "Running"):
            return "nas_up"
        return "nas_reachable"

    if st is None:
        return ("nas_down_tailscale_down" if available()
                else "nas_down_tailscale_missing")

    if not st["self_online"] or (st["backend"] and st["backend"] != "Running"):
        return "nas_down_tailscale_down"

    host = peer_for_path(root)
    if host and peer_online(host, st) is False:
        return "nas_down_peer_offline"
    return "nas_down"


def diagnose_label(code):
    """Human clause for Settings / logs. Empty string when nothing to say."""
    return {
        "nas_up": "Tailscale up",
        "nas_reachable": "",
        "nas_down": "",
        "nas_down_tailscale_down": "Tailscale down",
        "nas_down_peer_offline": "Tailscale peer offline",
        "nas_down_tailscale_missing": "",
        "off": "",
    }.get(code, "")