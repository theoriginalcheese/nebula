"""OBS metadata formatters — titlebar version + hero res/fps chip.

No OBS, no Tk. These are the pure helpers that turn GetVersion /
GetVideoSettings payloads into the strings the frames draw.

    python tests/test_obs_meta.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.gui import format_video_label, short_obs_version

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


check("short version keeps major.minor", short_obs_version("30.2.3") == "30.2")
check("short version passes through two-part", short_obs_version("30.2") == "30.2")
check("short version empty stays empty", short_obs_version("") == "")
check("short version None stays empty", short_obs_version(None) == "")

label = format_video_label({
    "baseWidth": 2560, "baseHeight": 1440,
    "fpsNumerator": 60, "fpsDenominator": 1,
})
check("video label matches frame 2a", label == "2560\u00d71440 \u00b7 60 fps", label)

label59 = format_video_label({
    "baseWidth": 1920, "baseHeight": 1080,
    "fpsNumerator": 60000, "fpsDenominator": 1001,
})
check("video label handles fractional fps", "1920\u00d71080" in label59 and "fps" in label59,
      label59)

check("video label blank when incomplete", format_video_label({"baseWidth": 1920}) == "")
check("video label blank on None", format_video_label(None) == "")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
