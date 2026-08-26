"""fsprobe.isdir_within: bounded probes + negative-verdict memo.

``os.path.isdir`` on a dead mapped drive blocks 20-60s inside the OS
redirector. The bounded probe abandons the call after ``timeout``, but the
abandoned thread stays stuck until the OS gives up - so a polling caller on
a dead path would stack one leaked thread per tick. The memo remembers
"not a dir" for a short TTL so the cost is one probe per TTL window.

    python tests/test_fsprobe.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import fsprobe

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


work = tempfile.mkdtemp(prefix="nebula-fsprobe-")
real = os.path.join(work, "real")
os.makedirs(real)

# Baseline behaviour on live paths.
check("existing dir is True", fsprobe.isdir_within(real) is True)
check("missing dir is False",
      fsprobe.isdir_within(os.path.join(work, "nope")) is False)
check("empty path is False", fsprobe.isdir_within("") is False)
check("None-ish path is False", fsprobe.isdir_within("   ") is False)

# Negative memo: second call within TTL does not re-probe (count invocations).
calls = {"n": 0}
_real_isdir = os.path.isdir


def counting(p):
    calls["n"] += 1
    return _real_isdir(p)


fsprobe.os.path.isdir = counting  # same module object the helper reads
try:
    missing = os.path.join(work, "ghost")
    fsprobe._neg_until.pop(fsprobe._key(missing), None)
    fsprobe.isdir_within(missing)
    n1 = calls["n"]
    fsprobe.isdir_within(missing)
    fsprobe.isdir_within(missing)
    check("negative verdict memoised", calls["n"] == n1, (n1, calls["n"]))

    # A known-good path is never negative-cached.
    fsprobe.isdir_within(real)
    n2 = calls["n"]
    fsprobe.isdir_within(real)
    check("positive results not memoised", calls["n"] > n2, (n2, calls["n"]))
finally:
    fsprobe.os.path.isdir = _real_isdir

# Timeout path returns quickly even against a hanging probe.
def hanging(_p):
    time.sleep(30)


fsprobe.os.path.isdir = hanging
try:
    t0 = time.monotonic()
    r = fsprobe.isdir_within(os.path.join(work, "slow"), timeout=0.3)
    dt = time.monotonic() - t0
finally:
    fsprobe.os.path.isdir = _real_isdir
check("timeout honoured", r is False and dt < 2.0, "%.2fs" % dt)
check("timeout result memoised",
      fsprobe.isdir_within(os.path.join(work, "slow"), timeout=0.3) is False)

# forget(): ground truth elsewhere must be able to invalidate the memo -
# without this, an outage shorter than _NEG_TTL_S leaves callers blind to
# recovery for the rest of the TTL (the offloader's exact bug).
gone = os.path.join(work, "recovering")
fsprobe.isdir_within(gone)                       # memoise False
os.makedirs(gone)                                # path comes back
check("memo hides recovery within TTL",
      fsprobe.isdir_within(gone) is False)
fsprobe.forget(gone)
check("forget clears the memo - next probe is real",
      fsprobe.isdir_within(gone) is True)
fsprobe.forget("")                                # empty/no-op safe
fsprobe.forget(None)                              # None-ish safe
check("forget tolerates empty/None paths", True)

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print("%-4s %-38s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%d/%d passed" % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)
