"""Clips pane - frame 2b, plus the delete rule that outranks it.

Builds a fake recording root so the assertions don't depend on what happens to
be on this machine's D: drive.

    python tests/test_clips.py
"""
import os
import shutil
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


root = tempfile.mkdtemp(prefix="nebula-clips-")
made = []
for game, names in (("Helldivers 2", ["a.mkv", "b.mkv", "c.mkv"]),
                    ("Elden Ring", ["d.mkv"]),
                    ("Factorio", ["e.mp4"])):
    os.makedirs(os.path.join(root, game))
    for i, n in enumerate(names):
        p = os.path.join(root, game, n)
        with open(p, "wb") as f:
            f.write(b"0" * (1024 * (i + 1)))
        made.append(p)
# Give them distinct mtimes so sorting is observable.
for i, p in enumerate(made):
    os.utime(p, (time.time() - i * 3600, time.time() - i * 3600))

config = load_config()
config["recording_root"] = root

app = AppWindow(config, Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=120):
    """Short pump. Safe *inside* mainloop; see the note below on why the initial
    scan can't be waited for this way."""
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


def rows():
    return app._rec_list.winfo_children()


def row_text(widget):
    out = []
    for w in (widget, *widget.winfo_children()):
        try:
            out.append(str(w.cget("text")))
        except Exception:
            pass
        for inner in w.winfo_children():
            try:
                out.append(str(inner.cget("text")))
            except Exception:
                pass
    return " ".join(out)


# The clips scan runs on a worker and marshals back through _ui() -> root.after.
# Tk REFUSES a cross-thread after() when the loop is driven by update()-pumping,
# and _ui() swallows that, so an update()-pumped test sees the results never
# arrive (CLAUDE.md). Everything below therefore runs under a real mainloop.
def run():

    check("all clips listed, not folders", len(rows()) == 5, len(rows()))
    check("row shows the relative path",
          any("Helldivers 2/" in row_text(r) for r in rows()),
          row_text(rows()[0])[:70] if rows() else "")
    # Initials are word-initials: "Helldivers 2" -> "H2". The frame draws "HD",
    # which isn't derivable from the name - so the rule wins over the pixel.
    check("game initials chip", any("H2" in row_text(r) for r in rows()))

    # Header counts are real.
    sub = app.bg.itemcget(app._rec_sub, "text")
    check("header counts the clips", "5 clips" in sub, sub[:70])

    # By-game sidebar with counts.
    side = " ".join(str(w.cget("text")) for r in app._clip_games.winfo_children()
                    for w in r.winfo_children())
    check("by-game sidebar lists games", "Helldivers 2" in side and "Elden Ring" in side,
          side[:80])
    check("by-game sidebar carries counts", "3" in side and "5" in side, side[:80])

    # ---- sort ----
    app._clip_sort.set("Largest")
    app._render_clips_rows()
    settle(120)
    check("sort by largest puts the biggest first",
          "c.mkv" in row_text(rows()[0]), row_text(rows()[0])[:60])
    app._clip_sort.set("Newest")
    app._render_clips_rows()
    settle(120)
    check("sort by newest puts the newest first",
          "a.mkv" in row_text(rows()[0]), row_text(rows()[0])[:60])

    # ---- search ----
    app._clip_search.insert(0, "elden")
    app._render_clips_rows()
    settle(120)
    check("search filters rows", len(rows()) == 1, len(rows()))
    app._clip_search.delete(0, "end")
    app._render_clips_rows()
    settle(120)
    check("clearing search restores rows", len(rows()) == 5, len(rows()))

    # ---- game filter ----
    app._clip_filter_game = "Helldivers 2"
    app._render_clips_rows()
    settle(120)
    check("game filter narrows to that game", len(rows()) == 3, len(rows()))
    app._clip_filter_game = None
    app._render_clips_rows()
    settle(120)

    # ---- empty state is the min-clip note only ----
    app._clip_search.insert(0, "zzz-no-match")
    app._render_clips_rows()
    settle(120)
    text = " ".join(row_text(r) for r in rows())
    check("empty state mentions min_clip_seconds", "min_clip_seconds" in text, text[:80])
    check("empty state says nothing else", len(rows()) == 1, len(rows()))
    app._clip_search.delete(0, "end")
    app._render_clips_rows()
    settle(120)

    # ---- delete respects copy-verify-then-delete ----
    target = app._clips[0]
    warned = {"n": 0}
    asked = {"n": 0}
    gui.tkinter.messagebox.showwarning = lambda *a, **k: warned.__setitem__("n", warned["n"] + 1)
    gui.tkinter.messagebox.askyesno = lambda *a, **k: (asked.__setitem__("n", asked["n"] + 1), False)[1]


    class StubOffloader:
        enabled = True

        def __init__(self, pending):
            self._pending = pending

        def pending_paths(self):
            return self._pending


    app.offloader = StubOffloader({target["path"]})
    app._delete_clip(target)
    check("refuses to delete a clip with no verified NAS copy", warned["n"] == 1, warned)
    check("no confirm dialog when refusing", asked["n"] == 0, asked)
    check("file still on disk", os.path.exists(target["path"]))

    # Once it has drained from the queue, it asks first.
    app.offloader = StubOffloader(set())
    app._delete_clip(target)
    check("asks before deleting an offloaded clip", asked["n"] == 1, asked)
    check("declining leaves the file alone", os.path.exists(target["path"]))

    # Confirm -> actually gone, and the row disappears.
    gui.tkinter.messagebox.askyesno = lambda *a, **k: True
    app._delete_clip(target)
    settle(200)
    check("confirmed delete removes the file", not os.path.exists(target["path"]))
    check("deleted clip drops out of the list", len(rows()) == 4, len(rows()))

    # With offload disabled entirely it still confirms rather than deleting silently.
    app.offloader = None
    asked["n"] = 0
    gui.tkinter.messagebox.askyesno = lambda *a, **k: (asked.__setitem__("n", asked["n"] + 1), False)[1]
    app._delete_clip(app._clips[0])
    check("still confirms when offload is off", asked["n"] == 1, asked)

    check("no callback exceptions", not callback_errors,
          callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")


    app.root.quit()


app.root.after(50, lambda: app._show_view("clips"))
app.root.after(1600, run)
app.root.after(20000, app.root.quit)   # safety net
app.root.mainloop()

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
shutil.rmtree(root, ignore_errors=True)
sys.exit(0 if passed_all else 1)
