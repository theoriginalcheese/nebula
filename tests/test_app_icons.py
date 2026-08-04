"""Games-pane icons: the three layers, and the rule about what gets synced.

    python tests/test_app_icons.py

The one that matters most is `paths are never written into games.json`. An exe
path is machine-specific and games.json merges across devices, so a path
leaking in there would be pushed to GitHub and pulled onto a machine where it
is wrong - the same class of bug as the classification merge in CLAUDE.md,
which cost real data.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import app_icons, design_v3 as dv

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---- the sidecar is separate from the synced classification data ----------

check("paths live beside the config, not in games.json",
      os.path.basename(app_icons.PATHS_FILE) == "app_paths.json"
      and "games.json" not in app_icons.PATHS_FILE,
      app_icons.PATHS_FILE)

check("icons cache to their own directory",
      os.path.basename(app_icons.ICON_DIR) == "icons", app_icons.ICON_DIR)

import obsauto.classifier as classifier_mod
src = open(classifier_mod.__file__, encoding="utf-8").read()
check("the classifier knows nothing about paths or icons",
      "app_icons" not in src and "app_paths" not in src)

# ---- layer 3: the monogram is deterministic and inside the palette --------

palette = {hex_value for hex_value, _ in dv.ACCENTS.values()}
names = ["Honkai Star rail", "Minecraft", "Roblox", "ZZZ", "some.exe", ""]
hues = {n: app_icons._hue_for(n) for n in names}

check("every monogram hue is one design_v3 already owns",
      all(h in palette for h in hues.values()),
      sorted(set(hues.values()) - palette))
check("the same name always gets the same hue",
      all(app_icons._hue_for(n) == hues[n] for n in names))
check("different names mostly get different hues",
      len(set(hues[n] for n in names[:4])) >= 3,
      [hues[n] for n in names[:4]])

check("initials come from the words, not the string",
      (app_icons._initials("Honkai Star rail"),
       app_icons._initials("Minecraft"),
       app_icons._initials("dwm.exe"),
       app_icons._initials("")) == ("HS", "MI", "DW", "?"),
      [app_icons._initials(x) for x in ("Honkai Star rail", "Minecraft", "dwm.exe", "")])

tile = app_icons.monogram("Honkai Star rail")
check("the tile is the stored size and has alpha",
      tile.size == (app_icons.SIZE, app_icons.SIZE) and tile.mode == "RGBA", tile.size)
check("the tile is not blank",
      tile.getchannel("A").getextrema()[1] > 0
      and len(set(tile.convert("L").getdata())) > 4,
      len(set(tile.convert("L").getdata())))
# A monogram whose glyph is 11px on a 64px tile is a speck, which is what
# Pillow's built-in bitmap font gives you if nothing catches it.
glyph_px = sum(1 for p in tile.convert("L").getdata() if p > 140)
check("the glyph is a real size, not the default bitmap font",
      glyph_px > 60, glyph_px)

# ---- layer 2: a real executable -------------------------------------------

probe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe")
if os.path.exists(probe):
    img = app_icons.extract(probe)
    check("a real executable yields a real icon", img is not None and img.size == (64, 64),
          img.size if img else None)
    if img:
        check("the extracted icon is not fully transparent",
              img.getchannel("A").getextrema()[1] > 0)
        check("the extracted icon is not one flat colour",
              len(set(img.convert("RGB").getdata())) > 16,
              len(set(img.convert("RGB").getdata())))
else:  # pragma: no cover - not Windows
    check("explorer.exe present to extract from", False, probe)

check("a missing executable is a None, not a crash",
      app_icons.extract(r"Z:\nope\missing.exe") is None)
check("an empty path is a None, not a crash", app_icons.extract("") is None)

# ---- the caller-facing layer ----------------------------------------------

data = app_icons.png_bytes("definitely-not-installed.exe", "Never Seen")
check("an unknown app still gets bytes back", data[:8] == b"\x89PNG\r\n\x1a\n", data[:8])
check("the same unknown app is memoised",
      app_icons.png_bytes("definitely-not-installed.exe", "Never Seen") is data)

url = app_icons.data_url("definitely-not-installed.exe", "Never Seen")
check("data_url is a PNG data URL", url.startswith("data:image/png;base64,"), url[:32])

check("the memo cannot grow without bound", app_icons.MEMO_MAX <= 512, app_icons.MEMO_MAX)

# A monogram is arithmetic on the name; caching it to disk would only create a
# file to invalidate on the day the executable finally turns up.
before = set(os.listdir(app_icons.ICON_DIR)) if os.path.isdir(app_icons.ICON_DIR) else set()
app_icons.png_bytes("still-not-installed.exe", "Also Never Seen")
after = set(os.listdir(app_icons.ICON_DIR)) if os.path.isdir(app_icons.ICON_DIR) else set()
check("a generated tile is not written to the icon cache", before == after,
      sorted(after - before))

# ---- remember() -----------------------------------------------------------

original = app_icons.PATHS_FILE
with tempfile.TemporaryDirectory() as tmp:
    app_icons.PATHS_FILE = os.path.join(tmp, "app_paths.json")
    app_icons._paths = None
    app_icons.remember(r"C:\Games\Thing\thing.exe")
    check("remember keys by lowercase basename",
          app_icons.known_path("thing.exe") == r"C:\Games\Thing\thing.exe",
          app_icons.known_path("thing.exe"))
    check("lookup is case-insensitive",
          app_icons.known_path("THING.EXE") == r"C:\Games\Thing\thing.exe")
    app_icons.remember(r"D:\Moved\thing.exe")
    check("a moved executable replaces the old path",
          app_icons.known_path("thing.exe") == r"D:\Moved\thing.exe",
          app_icons.known_path("thing.exe"))
    check("the sidecar is on disk", os.path.exists(app_icons.PATHS_FILE))
    app_icons.remember("")
    app_icons.remember(None)
    check("an empty path is ignored rather than stored",
          "" not in app_icons._load_paths())
app_icons.PATHS_FILE = original
app_icons._paths = None

# ---- report ---------------------------------------------------------------

failed = sum(1 for _, ok, _ in results if not ok)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<56} {detail}")
print(f"\n{'ALL PASS (%d checks)' % len(results) if not failed else '%d of %d FAILED' % (failed, len(results))}")
sys.exit(1 if failed else 0)
