"""config.json file I/O: round-trip, corrupt-file quarantine, atomic save.

    python tests/test_config_io.py

The pane-level rules live in test_settings.py ("never silently drop an
unknown key", saves on blur only). This file pins the *file* behaviour:
unknown keys survive a round-trip, a corrupt file falls back to defaults
with a log trail and is quarantined as .corrupt, and save_config leaves no
.tmp behind (write-then-replace, so a crash mid-save can't nuke the config).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import app_log
from obsauto.config import DEFAULTS, load_config, save_config

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


tmp = tempfile.mkdtemp(prefix="nebula-config-io-")
app_log.LOG_DIR = tmp
app_log.LOG_FILE = os.path.join(tmp, "obsauto.log")
app_log._logger = None  # rebind logging to the temp dir
app_log.setup_logging()  # production boots this before any config I/O

cfg_file = os.path.join(tmp, "config.json")

# --- 1. missing file -> defaults written out -----------------------------
import obsauto.config as cfgmod
cfgmod.CONFIG_FILE = cfg_file

cfg = load_config()
check("missing file -> DEFAULTS returned",
      all(cfg[k] == v for k, v in DEFAULTS.items()))
check("missing file -> config.json created",
      os.path.isfile(cfg_file))

# --- 2. unknown keys survive a round-trip ---------------------------------
cfg["some_future_key"] = "keep me"
cfg["obs_port"] = 4460
save_config(cfg)
cfg2 = load_config()
check("unknown key kept on round-trip",
      cfg2.get("some_future_key") == "keep me")
check("edited value survives round-trip", cfg2.get("obs_port") == 4460)

# --- 3. corrupt file -> defaults + quarantine + log trail -----------------
with open(cfg_file, "w", encoding="utf-8") as f:
    f.write('{"obs_host": "localhost", TRUNCATED')
cfg3 = load_config()
check("corrupt file -> defaults returned",
      cfg3.get("obs_port") == DEFAULTS["obs_port"], cfg3.get("obs_port"))
check("corrupt file quarantined as .corrupt",
      os.path.isfile(cfg_file + ".corrupt") and not os.path.isfile(cfg_file))
with open(app_log.LOG_FILE, encoding="utf-8") as f:
    log_text = f.read()
check("corrupt load left a log trail", "unreadable" in log_text,
      log_text[-300:])

# Next load starts clean (quarantined file no longer re-fails).
cfg4 = load_config()
check("post-quarantine load is clean defaults",
      os.path.isfile(cfg_file) and os.path.isfile(cfg_file + ".corrupt"))

# --- 4. atomic save leaves no .tmp ----------------------------------------
save_config(cfg4)
check("no stray .tmp after successful save",
      not os.path.exists(cfg_file + ".tmp"))

# A pre-existing stale .tmp does not break saving.
with open(cfg_file + ".tmp", "w", encoding="utf-8") as f:
    f.write("stale")
save_config(cfg4)
check("stale .tmp overwritten by save",
      not os.path.exists(cfg_file + ".tmp") and os.path.isfile(cfg_file))

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
