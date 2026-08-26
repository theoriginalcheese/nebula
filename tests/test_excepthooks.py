"""Process-level crash capture for the v4 (no-Tk) app.

    python tests/test_excepthooks.py

The legacy Tk shell had report_callback_exception, but spike/app.py has no
Tk root: under pythonw an uncaught exception on the main thread or in any
worker/JS-bridge thread printed to a stderr that does not exist. These checks
pin the install_excepthooks() contract: both hooks land in the app log,
existing hooks are chained, install is idempotent, and faulthandler is on
for native crashes.
"""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import app_log

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# Point logging at a throwaway dir before anything initialises it.
tmp = tempfile.mkdtemp(prefix="nebula-excepthook-test-")
app_log.LOG_DIR = tmp
app_log.LOG_FILE = os.path.join(tmp, "obsauto.log")
app_log.NATIVE_CRASH_FILE = os.path.join(tmp, "crash-native.log")
app_log._logger = None  # force setup_logging() to bind to the temp paths

_prev_sys = sys.excepthook
_prev_thr = threading.excepthook
_chained = {"sys": 0, "thr": 0}

sys.excepthook = lambda *a: _chained.__setitem__("sys", _chained["sys"] + 1)
threading.excepthook = lambda args: _chained.__setitem__(
    "thr", _chained["thr"] + 1)

app_log.install_excepthooks()
check("faulthandler enabled after install", __import__("faulthandler").is_enabled())

# Idempotent: a second install must not wrap the hooks again.
app_log.install_excepthooks()
app_log.install_excepthooks()

done = threading.Event()
seen = {}

# Built dynamically so the formatted traceback's *source line* (which shows
# the expression, not the value) cannot double-count the marker.
_MARKER = "marker-" + "worker-crash"


def boom():
    seen["t"] = threading.current_thread().name
    raise RuntimeError(_MARKER)


t = threading.Thread(target=boom, name="bridge-sim", daemon=True)
t.start()
t.join(timeout=10)
check("worker thread finished (hook did not hang)", not t.is_alive())

with open(app_log.LOG_FILE, encoding="utf-8") as f:
    log_text = f.read()
check("worker crash reached the app log",
      "marker-worker-crash" in log_text, log_text[-400:])
check("crash tagged with thread name", "bridge-sim" in log_text)
check("logged exactly once despite triple install",
      log_text.count("marker-worker-crash") == 1)
check("pre-existing thread hook still called", _chained["thr"] == 1,
      _chained)

# Main-thread hook: invoke it directly rather than crashing this test run.
try:
    raise ValueError("marker-main-crash")
except ValueError:
    sys.excepthook(*sys.exc_info())

with open(app_log.LOG_FILE, encoding="utf-8") as f:
    log_text = f.read()
check("main-thread crash reaches the app log",
      "marker-main-crash" in log_text and "main thread" in log_text)
check("pre-existing sys hook still called", _chained["sys"] == 1, _chained)

# Restore process state so later test files are unaffected.
sys.excepthook = _prev_sys
threading.excepthook = _prev_thr
app_log._hooks_installed = False

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
