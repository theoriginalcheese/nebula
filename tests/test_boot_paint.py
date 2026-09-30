"""Boot must paint even when the bridge is a tick late.

The page used to treat window.pywebview.api (an empty object) as ready,
call config()/snapshot() before the methods existed, then throw on
dashMeta.blocks inside the same try as the snapshot poll. One rejection
left the HTML placeholders — "Looking for OBS", "data stuck" — up for
the whole process, while Python had already connected to OBS.

    python tests/test_boot_paint.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, "spike", "web", "app.js")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    src = open(APP_JS, encoding="utf-8").read()

    check(
        "ready waits for snapshot function",
        'typeof api.snapshot !== "function"' in src
        and 'typeof api.config !== "function"' in src,
    )
    check(
        "ready does not resolve on an empty api",
        "window.pywebview && window.pywebview.api && (resolve(), true)" not in src,
    )
    check(
        "add-module tile tolerates a missing dashboard",
        "if (!tile || !dashMeta) return;" in src,
    )
    check(
        "null config does not read .dashboard",
        "const dash = (cfg && cfg.dashboard) || DASH_FALLBACK;" in src,
    )
    check(
        "showPane throw cannot skip the poll",
        "try { showPane(bootPane); } catch (e) { fail(\"data\", e); }" in src
        and src.find("setTimeout(pollLoop, 400)") > src.find("try { showPane(bootPane); }"),
    )
    check(
        "a rejected snapshot is not branded data stuck",
        'connEl.textContent = "data stuck"' not in src,
    )
    check(
        "boot retries config until it lands",
        "if (!bootCfg)" in src and "await ensureBoot()" in src,
    )

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
