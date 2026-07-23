"""Steam-side classification: figure out which installed Steam apps are
actually games (vs tools/DLC/servers) using Steam's own free, keyless
appdetails API - no local/paid AI needed.

Flow:
  1. Find every Steam library folder (registry InstallPath + libraryfolders.vdf).
  2. Parse each steamapps/appmanifest_<id>.acf for {appid, name, installdir}.
  3. Map installdir (the folder name under .../common/) -> (appid, name).
  4. Query store.steampowered.com/api/appdetails?appids=<id> (cached to disk)
     and read result.type: "game" vs "dlc"/"tool"/"application"/"demo".
"""

import json
import os
import re
import time

import requests

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows dev fallback
    winreg = None

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "steam_appid_cache.json")

# Steam's own store API tags these as type "game" for store/algorithm
# reasons even though they're actually utilities, not games - confirmed by
# checking the live API response. Override rather than trust the tag for
# these specific known cases.
KNOWN_NON_GAME_APPIDS = {
    "431960",  # Wallpaper Engine
    "993090",  # Lossless Scaling
}


def _read_steam_install_path():
    if winreg is None:
        return None
    for hive, key in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    ):
        try:
            with winreg.OpenKey(hive, key) as k:
                value, _ = winreg.QueryValueEx(k, "InstallPath")
                if value and os.path.isdir(value):
                    return value
        except OSError:
            continue
    return None


def _parse_vdf_paths(vdf_text):
    """Extract "path" values from Valve's KeyValue libraryfolders.vdf."""
    return re.findall(r'"path"\s*"([^"]+)"', vdf_text)


def find_library_folders():
    """Return every steamapps/common root Steam knows about."""
    install_path = _read_steam_install_path()
    libraries = []
    if install_path:
        libraries.append(install_path)

    vdf_candidates = [
        os.path.join(p, "steamapps", "libraryfolders.vdf") for p in libraries
    ]
    for vdf_path in vdf_candidates:
        if not os.path.exists(vdf_path):
            continue
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        for path in _parse_vdf_paths(text):
            path = path.replace("\\\\", "\\")
            if path not in libraries:
                libraries.append(path)

    return [os.path.join(lib, "steamapps", "common") for lib in libraries if os.path.isdir(lib)]


def scan_app_manifests():
    """Return {installdir_lower: {"appid": ..., "name": ...}} across all libraries."""
    apps = {}
    install_path = _read_steam_install_path()
    if not install_path:
        return apps

    libraries = [install_path]
    vdf_path = os.path.join(install_path, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf_path):
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            for path in _parse_vdf_paths(text):
                path = path.replace("\\\\", "\\")
                if path not in libraries:
                    libraries.append(path)
        except OSError:
            pass

    for lib in libraries:
        steamapps_dir = os.path.join(lib, "steamapps")
        if not os.path.isdir(steamapps_dir):
            continue
        for entry in os.listdir(steamapps_dir):
            if not (entry.startswith("appmanifest_") and entry.endswith(".acf")):
                continue
            manifest_path = os.path.join(steamapps_dir, entry)
            try:
                with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue

            appid_m = re.search(r'"appid"\s*"(\d+)"', text)
            name_m = re.search(r'"name"\s*"([^"]+)"', text)
            installdir_m = re.search(r'"installdir"\s*"([^"]+)"', text)
            if not (appid_m and installdir_m):
                continue

            apps[installdir_m.group(1).lower()] = {
                "appid": appid_m.group(1),
                "name": name_m.group(1) if name_m else installdir_m.group(1),
                "path": os.path.join(steamapps_dir, "common", installdir_m.group(1)),
            }

    return apps


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_cache(cache):
    # Same merge-before-write reasoning as classifier.py's _save(): this file
    # may live in a folder synced with another machine.
    merged = {**_load_cache(), **cache}
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
    except OSError:
        pass


def classify_appid(appid, cache=None, log=lambda msg: None):
    """Return (is_game: bool, display_name: str | None) for a Steam AppID.

    Uses store.steampowered.com/api/appdetails, which is free and needs no
    API key. Result is cached to disk so we only hit the network once per app.
    """
    if appid in KNOWN_NON_GAME_APPIDS:
        return False, None

    cache = cache if cache is not None else _load_cache()
    cached = cache.get(appid)
    if cached is not None:
        return cached.get("is_game", False), cached.get("name")

    try:
        resp = requests.get(
            APPDETAILS_URL, params={"appids": appid, "cc": "us", "l": "en"}, timeout=10
        )
        resp.raise_for_status()
        data = resp.json().get(appid, {})
        if not data.get("success"):
            is_game, name = False, None
        else:
            app_data = data.get("data", {})
            is_game = app_data.get("type") == "game"
            name = app_data.get("name")
        cache[appid] = {"is_game": is_game, "name": name}
        _save_cache(cache)
        time.sleep(1)  # be polite to Steam's public endpoint
        return is_game, name
    except (requests.RequestException, ValueError) as e:
        log(f"[Steam API] Lookup failed for appid {appid}: {e}")
        return False, None


def build_steam_game_index(log=lambda msg: None):
    """Return {installdir_lower: display_name} for installdir's that are real games."""
    manifests = scan_app_manifests()
    cache = _load_cache()
    index = {}
    for installdir, info in manifests.items():
        is_game, store_name = classify_appid(info["appid"], cache=cache, log=log)
        if is_game:
            index[installdir] = store_name or info["name"]
    return index
