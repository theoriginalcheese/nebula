"""The session-ribbon model (7b) and the storage forecast maths (7c).

Both read sessions.jsonl and nothing else, so both can be tested without a
window, a disk or a clock. 7c says of its arithmetic "implement exactly", so
these assertions are mostly that - worked examples with numbers chosen so the
right answer is obvious by hand.

    python tests/test_forecast.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import forecast, session_log
from obsauto.config import DEFAULTS

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


GB = forecast.GB
HOUR = 3600
DAY = 86400
NOW = time.mktime((2026, 7, 27, 12, 0, 0, 0, 0, -1))


def ev(kind, ts, **extra):
    row = {"ts": ts, "type": kind}
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# 7b - spans
# ---------------------------------------------------------------------------
rows = [
    ev("rec_start", NOW - 4 * HOUR, game="Helldivers 2"),
    ev("idle_in", NOW - 3.5 * HOUR, game="Helldivers 2"),
    ev("idle_out", NOW - 3.4 * HOUR, game="Helldivers 2"),
    ev("mark", NOW - 3.2 * HOUR, game="Helldivers 2"),
    ev("rec_stop", NOW - 3 * HOUR, game="Helldivers 2", path="a.mkv",
       duration=3600, size=4 * GB),
    ev("rec_start", NOW - 2 * HOUR, game="Factorio"),
    ev("rec_stop", NOW - 1 * HOUR, game="Factorio", path="b.mkv",
       duration=3600, size=2 * GB),
    ev("rec_start", NOW - 0.5 * HOUR, game="Helldivers 2"),   # still running
]
spans = session_log.spans(rows, now=NOW)
check("one span per recording, plus the live one", len(spans) == 3, len(spans))
check("spans carry their game",
      [s["game"] for s in spans] == ["Helldivers 2", "Factorio", "Helldivers 2"],
      [s["game"] for s in spans])
check("a finished span isn't live", spans[0]["live"] is False)
check("the unclosed span is live", spans[2]["live"] is True)
check("a live span runs to now", spans[2]["end"] == NOW, spans[2]["end"])
check("idle gaps land inside their span",
      len(spans[0]["gaps"]) == 1 and abs(
          spans[0]["gaps"][0][1] - spans[0]["gaps"][0][0] - 0.1 * HOUR) < 1,
      spans[0]["gaps"])
check("marks land on their span", spans[0]["marks"] and not spans[1]["marks"],
      [len(s["marks"]) for s in spans])
check("the clip's path and size come through",
      spans[0]["path"] == "a.mkv" and spans[0]["size"] == 4 * GB,
      (spans[0]["path"], spans[0]["size"]))

summary = session_log.summarise(spans)
check("the header counts distinct games", summary["games"] == 2, summary)
check("the header counts marks", summary["marks"] == 1, summary)
# 2.5h of spans, one of which holds a 0.1h idle gap. The header answers
# "how long did I record", so the pause comes out - it used to be counted.
check("the header sums recorded time, pauses excluded",
      abs(summary["seconds"] - (1 + 1 + 0.5 - 0.1) * HOUR) < 1, summary)

# A log that begins mid-recording (a crash, a first run) must not lose the clip.
orphan = session_log.spans(
    [ev("rec_stop", NOW, game="Elden Ring", duration=1800, size=GB)], now=NOW)
check("a stop with no start still yields a span", len(orphan) == 1, orphan)
check("...starting duration-many seconds earlier",
      abs(orphan[0]["start"] - (NOW - 1800)) < 1, orphan[0]["start"])

# Two starts in a row (a missed stop) must not swallow the first.
doubled = session_log.spans([ev("rec_start", NOW - HOUR, game="A"),
                             ev("rec_start", NOW - 60, game="B")], now=NOW)
check("a missed stop still closes the earlier span", len(doubled) == 2, doubled)
check("an empty log has no spans", session_log.spans([], now=NOW) == [])

# ---------------------------------------------------------------------------
# 7c - the rates
# ---------------------------------------------------------------------------
# Three days, one hour each, 9 GB written per hour. GB/h = 9, h/day = 1.
easy = []
for d in (1, 2, 3):
    start = NOW - d * DAY
    easy += [ev("rec_start", start, game="G"),
             ev("rec_stop", start + HOUR, game="G", duration=HOUR, size=9 * GB)]
stats = forecast.rates(session_log.spans(easy, now=NOW), now=NOW)
check("GB per hour is bytes over hours recorded",
      abs(stats["gb_per_hour"] - 9.0) < 0.01, stats["gb_per_hour"])
check("hours per day averages only days WITH activity",
      abs(stats["hours_per_day"] - 1.0) < 0.01, stats["hours_per_day"])
check("days with activity are counted", stats["days_with_activity"] == 3, stats)

# The same three sessions spread over a fortnight must NOT report h/day of
# 3/14 - "mean over days WITH activity, not all 14".
sparse = []
for d in (1, 6, 13):
    start = NOW - d * DAY
    sparse += [ev("rec_start", start, game="G"),
               ev("rec_stop", start + 2 * HOUR, game="G", duration=2 * HOUR,
                  size=18 * GB)]
sparse_stats = forecast.rates(session_log.spans(sparse, now=NOW), now=NOW)
check("a weekend player isn't averaged into nothing",
      abs(sparse_stats["hours_per_day"] - 2.0) < 0.01,
      sparse_stats["hours_per_day"])

# Idle gaps are paused time - the file isn't growing, so they mustn't count.
paused = [ev("rec_start", NOW - 2 * HOUR, game="G"),
          ev("idle_in", NOW - 1.5 * HOUR, game="G"),
          ev("idle_out", NOW - 0.5 * HOUR, game="G"),
          ev("rec_stop", NOW, game="G", duration=2 * HOUR, size=10 * GB)]
paused_stats = forecast.rates(session_log.spans(paused, now=NOW), now=NOW)
check("idle time is not counted as recording time",
      abs(paused_stats["hours"] - 1.0) < 0.01, paused_stats["hours"])
check("...so GB/h reflects what was actually written",
      abs(paused_stats["gb_per_hour"] - 10.0) < 0.01, paused_stats["gb_per_hour"])

# Anything older than the window is out of it.
old = [ev("rec_start", NOW - 30 * DAY, game="G"),
       ev("rec_stop", NOW - 30 * DAY + HOUR, game="G", duration=HOUR, size=99 * GB)]
check("events outside the 14-day window are ignored",
      forecast.rates(session_log.spans(old, now=NOW), now=NOW)["hours"] == 0)

# ---------------------------------------------------------------------------
# 7c - the forecast
# ---------------------------------------------------------------------------
# 9 GB/h x 1 h/day = 9 GB/day. 90 GB free = 10 days.
result = forecast.forecast(90 * GB, 1000 * GB, session_log.spans(easy, now=NOW), now=NOW)
check("the forecast is ready with three days of history", result["ready"] is True)
check("days left = free / (GB per hour x hours per day)",
      abs(result["days_left"] - 10.0) < 0.05, result["days_left"])
check("it states a date, not a ratio", result["full_on"] is not None)
check("the date is days_left away",
      abs(result["full_on"] - (NOW + 10 * DAY)) < 60, result["full_on"])
check("the projection is seven days of growth",
      abs(result["projected_bytes"] - 63 * GB) < GB, result["projected_bytes"])
check("the projection never exceeds what's free",
      forecast.forecast(10 * GB, 1000 * GB, session_log.spans(easy, now=NOW),
                        now=NOW)["projected_bytes"] <= 10 * GB)

# Two days of history is not three.
two = []
for d in (1, 2):
    start = NOW - d * DAY
    two += [ev("rec_start", start, game="G"),
            ev("rec_stop", start + HOUR, game="G", duration=HOUR, size=9 * GB)]
short = forecast.forecast(90 * GB, 1000 * GB, session_log.spans(two, now=NOW), now=NOW)
check("under three days there is no forecast", short["ready"] is False)
check("...and it says how many more are needed", short["days_needed"] == 1, short)
check("...rather than guessing a date", short["days_left"] is None)

check("no history at all is not an error",
      forecast.forecast(90 * GB, 1000 * GB, [], now=NOW)["ready"] is False)

# Rounding, exactly as specified.
check("under a day shows hours", forecast.days_left_label(0.5) == "12 hours",
      forecast.days_left_label(0.5))
check("one hour is singular", forecast.days_left_label(1 / 24.0) == "1 hour",
      forecast.days_left_label(1 / 24.0))
check("over sixty days is capped", forecast.days_left_label(90) == "60+ days",
      forecast.days_left_label(90))
check("in between is whole days", forecast.days_left_label(6.2) == "6 days",
      forecast.days_left_label(6.2))
check("one day is singular", forecast.days_left_label(1.0) == "1 day")
check("no forecast means no label", forecast.days_left_label(None) == "")

check("the gain from a cull is in days",
      abs(forecast.cull_gain_days(90 * GB, 9.0, 1.0) - 10.0) < 0.05,
      forecast.cull_gain_days(90 * GB, 9.0, 1.0))
check("no rate means no gain figure",
      forecast.cull_gain_days(90 * GB, None, 1.0) is None)

# ---------------------------------------------------------------------------
# 7c - what a cull would take
# ---------------------------------------------------------------------------
root = tempfile.mkdtemp(prefix="nebula-cull-")


def make(rel, age_days, size=1024):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"0" * size)
    when = time.time() - age_days * DAY
    os.utime(path, (when, when))
    return path


old_clip = make("Helldivers 2/old.mkv", 40)
new_clip = make("Helldivers 2/new.mkv", 2)
marked = make("Helldivers 2/marked.mkv", 40)
replay = make("Helldivers 2/Replays/saved.mkv", 40)
cached = make(".nebula/thumbs/old-1.webp", 40)

got = forecast.cull_candidates(root, 30, keep_marked=True, marked_paths=[marked])
names = sorted(os.path.basename(p) for p in got["files"])
check("a cull takes only what's old enough", names == ["old.mkv"], names)
check("recent clips are safe", "new.mkv" not in names)
check("marked clips are excluded", "marked.mkv" not in names)
check("replays are never culled", "saved.mkv" not in names)
check("the thumbnail cache isn't touched", "old-1.webp" not in names)
check("it reports the count and the total",
      got["count"] == 1 and got["bytes"] == 1024, got)

check("keep_marked off does include a marked clip",
      len(forecast.cull_candidates(root, 30, keep_marked=False,
                                   marked_paths=[marked])["files"]) == 2)
check("cull_after_days 0 turns it off",
      forecast.cull_candidates(root, 0)["count"] == 0)
check("a missing root is not an error",
      forecast.cull_candidates(os.path.join(root, "nope"), 30)["count"] == 0)

for key, want in forecast.DEFAULTS.items():
    if key in DEFAULTS:
        check(f"config carries {key}", DEFAULTS[key] == want,
              f"{DEFAULTS.get(key)!r} != {want!r}")

# ---------------------------------------------------------------------------
# The rendering of both, in a live window
# ---------------------------------------------------------------------------
import traceback

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto import design_v3 as dv
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

log = os.path.join(tempfile.mkdtemp(prefix="nebula-ribbon-"), "sessions.jsonl")
session_log.log_path = lambda: log
for row in rows:
    session_log.append(row["type"], game=row.get("game"),
                       **{k: v for k, v in row.items()
                          if k not in ("ts", "type", "game")})

app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=200):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


settle(300)
app._show_view("clips")
settle(300)

# 7b geometry, straight off the spec sheet.
check("the ribbon is the spec's height", dv.RIBBON_H == 188, dv.RIBBON_H)
check("track h 38, gap 3, radius 3 / 6 on ends",
      (dv.RIBBON_TRACK_H, dv.RIBBON_TRACK_GAP, dv.RIBBON_RADIUS,
       dv.RIBBON_END_RADIUS) == (38, 3, 3, 6),
      (dv.RIBBON_TRACK_H, dv.RIBBON_RADIUS, dv.RIBBON_END_RADIUS))
check("minimum block is 4px", dv.RIBBON_MIN_BLOCK == 4)
check("clip marks are 2px and overhang 5px",
      (dv.RIBBON_MARK_W, dv.RIBBON_MARK_OVERHANG) == (2, 5))
check("the idle hatch is 4px at .07",
      (dv.RIBBON_HATCH_PERIOD, dv.RIBBON_HATCH_ALPHA) == (4, 0.07))
check("the ribbon lives in the Clips pane",
      getattr(app, "_ribbon_geom", None) is not None)
check("it drew something", len(app._ribbon_items) > 1, len(app._ribbon_items))

summary_text = app.bg._c.itemcget(app._ribbon_summary, "text")
check("the header reports recorded time, games and marks",
      "recorded" in summary_text and "game" in summary_text
      and "mark" in summary_text, summary_text)

# "Per-game shade: lightness ±8% only - never a new hue."
lighter = gui._shift_lightness(dv.RIBBON_BLOCK_TOP, 0.08)
darker = gui._shift_lightness(dv.RIBBON_BLOCK_TOP, -0.08)
check("shading changes lightness", lighter != dv.RIBBON_BLOCK_TOP != darker)


def hue_of(hex_colour):
    import colorsys
    c = hex_colour.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)[0]


check("shading never changes the hue",
      abs(hue_of(lighter) - hue_of(dv.RIBBON_BLOCK_TOP)) < 0.01
      and abs(hue_of(darker) - hue_of(dv.RIBBON_BLOCK_TOP)) < 0.01,
      (hue_of(darker), hue_of(dv.RIBBON_BLOCK_TOP), hue_of(lighter)))

# Clicking a block fills the detail row.
live_spans = session_log.spans(now=time.time())
if live_spans:
    app._select_span(live_spans[0])
    settle(60)
    check("selecting a block fills the detail row",
          live_spans[0]["game"] in app.bg._c.itemcget(app._ribbon_detail, "text"),
          app.bg._c.itemcget(app._ribbon_detail, "text"))
    check("...and its sub-line carries the numbers",
          bool(app.bg._c.itemcget(app._ribbon_detail_sub, "text")),
          app.bg._c.itemcget(app._ribbon_detail_sub, "text"))

for name in dv.RIBBON_RANGES:
    app._set_ribbon_range(name)
    settle(60)
check("every range renders without error", app._ribbon_range == "Session",
      app._ribbon_range)
app._set_ribbon_range("Day")
settle(60)

# 7c: the rail states a date, and refuses to record on a full disk.
app._disk_usage = (5 * GB, 1000 * GB)
ok, reason = app.can_start_recording()
check("a nearly-full disk refuses a recording", ok is False, reason)
check("...and says why", "GB free" in reason, reason)
app._disk_usage = (500 * GB, 1000 * GB)
check("plenty of room records happily", app.can_start_recording()[0] is True)
app.config["disk_block_below_gb"] = 0
app._disk_usage = (1 * GB, 1000 * GB)
check("the floor can be turned off", app.can_start_recording()[0] is True)
app.config["disk_block_below_gb"] = 20

app._disk_usage = (500 * GB, 1000 * GB)
app._refresh_forecast()
settle(60)
check("with no history the rail shows no forecast",
      app.bg._c.itemcget(app._store_pct, "text") == "",
      app.bg._c.itemcget(app._store_pct, "text"))
check("...and says how much history it needs",
      "history" in app.bg._c.itemcget(app._store_note, "text"),
      app.bg._c.itemcget(app._store_note, "text"))

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

app.root.destroy()

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<54} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
