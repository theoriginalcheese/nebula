"""Print which Nebula binary/checkout you are looking at.

    python tools/nebula_identity.py

Stops the frozen-exe vs source-clone mix-up: toast (and every other UI)
judgement must name this identity first. The Aug 2026 confusion was agents
comparing capsule source to ``C:\\Users\\antho\\Nebula\\Nebula (1).exe``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from obsauto.paths import APP_DIR, RESOURCE_DIR
from obsauto.version import display_version, is_frozen, version_info


def _git(*args: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True,
        )
        return out.strip()
    except Exception:
        return ""


def identity() -> dict:
    info = version_info()
    data = {
        "display": display_version(),
        "frozen": is_frozen(),
        "kind": "frozen-exe" if is_frozen() else "source-checkout",
        "app_dir": os.path.abspath(APP_DIR),
        "resource_dir": os.path.abspath(RESOURCE_DIR),
        "repo_root": ROOT if not is_frozen() else "",
        "git_head": _git("rev-parse", "HEAD") if not is_frozen() else "",
        "git_branch": _git("branch", "--show-current") if not is_frozen() else "",
        "git_describe": info.get("describe") or _git("describe", "--tags", "--always", "--dirty"),
        "executable": sys.executable,
        "toast_surface": "obsauto/gui.py capsule (Tk)" if not is_frozen()
        else "whatever was baked into this exe",
        "spike_toast": "spike/web/toast.css (squared DWM card — NOT the Tk capsule)",
        "known_exe_data_dir": r"C:\Users\antho\Nebula",
        "known_source_dir": r"C:\Users\antho\Downloads\nebula",
    }
    return data


def banner(prefix: str = "[nebula-identity]") -> str:
    d = identity()
    lines = [
        f"{prefix} kind={d['kind']}  display={d['display']}",
        f"{prefix} app_dir={d['app_dir']}",
    ]
    if d["git_head"]:
        lines.append(
            f"{prefix} git={d['git_branch'] or '?'}@{d['git_head'][:12]}  "
            f"describe={d['git_describe']}"
        )
    lines.append(
        f"{prefix} toast UI: judge ONLY this process — never the frozen "
        f"exe beside {d['known_exe_data_dir']}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    data = identity()
    if "--json" in argv:
        print(json.dumps(data, indent=2))
    else:
        print(banner(""))
        print()
        print("fields:")
        for k, v in data.items():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
