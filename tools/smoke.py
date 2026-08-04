"""Visual smoke test: drive every pane and photograph it.

    python tools/smoke.py                  # every pane, plus palette and customise
    python tools/smoke.py --only clips     # one pane
    python tools/smoke.py --keep           # leave the app running afterwards

Why this exists
---------------
The v4 gate is 131 checks and every one of them is blind to what the window
*looks like*. Eight delegated jobs in a row passed the gate with a visible
defect; every one was caught by opening a PNG. This makes that loop one command
instead of a manual dance of goto_pane.txt writes and window hunting.

It photographs surfaces, it does not judge them. Compare each shot against its
frame in `design/ui-v3/frames/` - `tools/frames.py --only 2b` renders those.
A green run here means "nine surfaces rendered and none came back blank", which
is a much weaker claim than "they are correct".

Pane switching uses the dev-only `shots/goto_pane.txt` hook that app.js polls at
400ms; it is compiled out of a frozen build, so this runs against source only.
"""
import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import shoot  # noqa: E402

OUT_DIR = os.path.join(ROOT, "shots", "smoke")
GOTO = os.path.join(ROOT, "shots", "goto_pane.txt")

# pane -> the frame it is supposed to look like
PANES = [
    ("dashboard", "2a"),
    ("clips", "2b"),
    ("games", "2d"),
    ("macropad", "2e"),
    ("settings", "2c"),
]

# Surfaces that need their own boot, because they are entered by a URL switch
# rather than by a pane change.
BOOTS = [
    ("palette", "palette=1", "7e"),
    ("customise", "customise=1", "6h"),
]


class LaunchRefused(Exception):
    """The process we started exited instead of opening a window."""


def launch(url_args=""):
    """Start the app from source and wait for its window to actually exist."""
    cmd = [sys.executable, os.path.join(ROOT, "spike", "app.py"), "--show"]
    if url_args:
        cmd.append("--url=" + url_args)
    p = subprocess.Popen(cmd, cwd=ROOT)
    for _ in range(60):
        time.sleep(1.0)
        # Check the child before checking for a window. A second instance exits
        # on the single-instance mutex within a second, and shoot.windows()
        # would then cheerfully find the window belonging to the instance that
        # was ALREADY running - photographing whatever pane it happened to be
        # on and reporting it as the surface we asked for. That is exactly the
        # false green this tool exists to prevent: a `customise ok` line under
        # a screenshot of the Settings pane.
        if p.poll() is not None:
            raise LaunchRefused(
                "the app exited immediately (rc=%s) - almost certainly another "
                "Nebula is running, and ?%s needs its own boot. Quit the "
                "running one first." % (p.returncode, url_args or "-"))
        if shoot.windows("Nebula"):
            # The window exists, but WebView2 paints a frame or two later.
            time.sleep(4.0)
            return p
    p.terminate()
    raise SystemExit("app never opened a window")


def stop(p):
    try:
        p.terminate()
        p.wait(timeout=10)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    # pywebview's child processes outlive a terminate() on the parent often
    # enough that the next launch would hit the single-instance mutex.
    time.sleep(2.0)


def goto(pane):
    with open(GOTO, "w", encoding="utf-8") as fh:
        fh.write(pane)
    # Polled at 400ms, then the pane-change transition runs for --pane-change-ms.
    for _ in range(20):
        time.sleep(0.25)
        if not os.path.isfile(GOTO):
            break
    time.sleep(1.2)


def capture(name, frame):
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "%s.png" % name)
    try:
        shoot.shoot("Nebula", out, verify=True)
    except SystemExit as exc:
        print("  %-12s FAIL  %s" % (name, exc))
        return False
    print("  %-12s ok    %s  (frame %s)"
          % (name, os.path.relpath(out, ROOT).replace("\\", "/"), frame))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one pane name, or a boot switch name")
    ap.add_argument("--keep", action="store_true",
                    help="leave the last app instance running")
    a = ap.parse_args()

    if os.path.isfile(GOTO):
        os.remove(GOTO)

    panes = PANES
    boots = BOOTS
    if a.only:
        panes = [x for x in PANES if x[0] == a.only]
        boots = [x for x in BOOTS if x[0] == a.only]
        if not panes and not boots:
            raise SystemExit("unknown surface %r" % a.only)

    ok = failed = 0
    proc = None

    if panes:
        print("panes (one instance, switched via shots/goto_pane.txt)")
        proc = launch()
        try:
            for pane, frame in panes:
                goto(pane)
                if capture(pane, frame):
                    ok += 1
                else:
                    failed += 1
        finally:
            if not (a.keep and not boots):
                stop(proc)
                proc = None

    for name, url, frame in boots:
        print("%s (own boot: ?%s)" % (name, url))
        try:
            proc = launch(url)
        except LaunchRefused as exc:
            print("  %-12s FAIL  %s" % (name, exc))
            failed += 1
            continue
        try:
            if capture(name, frame):
                ok += 1
            else:
                failed += 1
        finally:
            if not (a.keep and name == boots[-1][0]):
                stop(proc)
                proc = None

    print("\n%d captured, %d failed -> %s"
          % (ok, failed, os.path.relpath(OUT_DIR, ROOT).replace("\\", "/")))
    print("Now LOOK at them. A blank-check pass is not a design review.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
