"""New bugs found while hunting sync / classification / phone / update code.

    python tests/test_hunt_sync.py
"""
import base64
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.classifier import merge_classifications
from obsauto import gamesync as gamesync_module
from obsauto.gamesync import GameSync, NasGameSync
from obsauto import settings_spec

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---------------------------------------------------------------------------
# Bug 1: merge_classifications never heals double-filing on the `base` side,
# only on `overlay`. A remote/on-disk copy that is already double-filed (old
# union-merge damage, or damage introduced before a fix shipped) survives a
# merge untouched whenever the overlay has no opinion on that key - and
# GameSync.push() writes that merged (still-damaged) result straight back to
# the shared store, so the corruption never heals.
# ---------------------------------------------------------------------------

def test_merge_heals_double_filing_on_either_side():
    # Damage lives in `base` (e.g. the remote copy); overlay has no opinion.
    damaged_base = {
        "games": {"starrail.exe": {"display_name": "Star Rail"}},
        "non_games": {"starrail.exe": True},
    }
    clean_overlay = {"games": {}, "non_games": {}}
    merged = merge_classifications(damaged_base, clean_overlay)
    check("base-side double-filing is healed: stays a game",
          "starrail.exe" in merged["games"], merged)
    check("base-side double-filing is healed: drops the non-game copy",
          "starrail.exe" not in merged["non_games"], merged)

    # Base damage heals even when the overlay is busy classifying something
    # else entirely - healing must not depend on the overlay mentioning the
    # damaged key.
    merged2 = merge_classifications(damaged_base, {
        "games": {}, "non_games": {"other.exe": True},
    })
    check("base-side healing happens alongside an unrelated overlay change",
          "starrail.exe" in merged2["games"]
          and "starrail.exe" not in merged2["non_games"], merged2)

    # A *deliberate* overlay reclassification still wins over base, healed or
    # not - healing must never override a real opinion.
    merged3 = merge_classifications(damaged_base, {
        "games": {}, "non_games": {"starrail.exe": True},
    })
    check("a genuine overlay reclassification still overrides base",
          "starrail.exe" not in merged3["games"]
          and "starrail.exe" in merged3["non_games"], merged3)


def test_gamesync_push_does_not_perpetuate_remote_double_filing():
    """A concrete, networked demonstration of the same bug via GameSync."""

    class FakeResponse:
        def __init__(self, status, payload=None):
            self.status_code = status
            self._payload = payload or {}

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("HTTP %s" % self.status_code)

    class FakeGitHub:
        def __init__(self, initial):
            self.body = json.dumps(initial).encode()
            self.sha = "sha0"
            self.puts = 0

        def get(self, url, headers=None, timeout=None):
            return FakeResponse(200, {
                "sha": self.sha,
                "content": base64.b64encode(self.body).decode(),
            })

        def put(self, url, headers=None, json=None, timeout=None):
            self.puts += 1
            self.body = base64.b64decode(json["content"])
            self.sha = "sha%d" % self.puts
            return FakeResponse(200, {"content": {"sha": self.sha}})

    remote_damaged = {
        "games": {"starrail.exe": {"display_name": "Star Rail"}},
        "non_games": {"starrail.exe": True},
    }
    fake = FakeGitHub(remote_damaged)
    gamesync_module.requests = fake
    sync = GameSync(
        {"github_token": "t", "github_gamedata_repo": "o/r",
         "github_gamedata_path": "games.json"},
        on_log=lambda m: None,
    )
    # Local classifier has classified an unrelated game; no opinion on
    # starrail.exe at all.
    local = {"games": {"other.exe": {"display_name": "Other"}}, "non_games": {}}
    out = sync.push(local)
    check("push succeeds", out is not None, out)
    check("push does not re-file starrail.exe as a non-game",
          "starrail.exe" not in (out or {}).get("non_games", {}), out)
    stored = json.loads(fake.body)
    check("the remote file itself is healed, not re-corrupted",
          "starrail.exe" in stored["games"]
          and "starrail.exe" not in stored.get("non_games", {}), stored)


def test_nas_push_does_not_perpetuate_double_filing():
    root = tempfile.mkdtemp(prefix="nebula-hunt-nas-heal-")
    nas_path = os.path.join(root, ".nebula", "games.json")
    os.makedirs(os.path.dirname(nas_path))
    with open(nas_path, "w", encoding="utf-8") as fh:
        json.dump({
            "games": {"starrail.exe": {"display_name": "Star Rail"}},
            "non_games": {"starrail.exe": True},
        }, fh)
    nas = NasGameSync({"nas_offload_root": root, "games_sync_nas": True},
                       on_log=lambda m: None)
    out = nas.push({"games": {"other.exe": {"display_name": "Other"}},
                     "non_games": {}})
    check("NAS push succeeds", out is not None, out)
    check("NAS push heals the double-filed entry rather than re-storing it",
          "starrail.exe" in (out or {}).get("games", {})
          and "starrail.exe" not in (out or {}).get("non_games", {}), out)
    with open(nas_path, encoding="utf-8") as fh:
        after = json.load(fh)
    check("the NAS file on disk is healed too",
          "starrail.exe" in after["games"]
          and "starrail.exe" not in after.get("non_games", {}), after)


# ---------------------------------------------------------------------------
# Bug 2: settings_spec.parse() has no branch for Field.kind == "bool", so it
# falls through to the int-parsing path. render() happily turns a bool value
# into "True"/"False" text, but parse() then cannot read that text back -
# every bool field ("replay_enabled", "cull_keep_marked", "run_as_administrator",
# "games_sync_nas", ...) fails with the nonsense error "needs a whole number"
# instead of round-tripping. Any caller that walks FIELDS generically and
# calls settings_spec.parse() directly (rather than special-casing "bool"
# itself first, the way spike/app.py's set_setting() does) can never change a
# boolean setting through text.
# ---------------------------------------------------------------------------

def test_bool_field_round_trips_through_render_and_parse():
    field = settings_spec.BY_KEY["replay_enabled"]
    check("bool field kind is really 'bool'", field.kind == "bool", field.kind)

    for stored in (True, False):
        text = settings_spec.render(field, stored)
        value, error = settings_spec.parse(field, text)
        check("parse(render(%r)) round-trips" % stored,
              value is stored and error is None, (text, value, error))

    value, error = settings_spec.parse(field, "true")
    check("lowercase 'true' parses to True", value is True and error is None,
          (value, error))
    value, error = settings_spec.parse(field, "false")
    check("lowercase 'false' parses to False", value is False and error is None,
          (value, error))

    value, error = settings_spec.parse(field, "banana")
    check("garbage is rejected with an error, not silently coerced",
          value is None and error is not None, (value, error))


def main():
    test_merge_heals_double_filing_on_either_side()
    test_gamesync_push_does_not_perpetuate_remote_double_filing()
    test_nas_push_does_not_perpetuate_double_filing()
    test_bool_field_round_trips_through_render_and_parse()
    passed_all = all(ok for _name, ok, _detail in results)
    for name, ok, detail in results:
        print("%s  %-58s %s" % ("PASS" if ok else "FAIL", name, detail))
    print("\n%s (%d checks)" % (
        "ALL PASS" if passed_all else "FAILURES PRESENT", len(results)))
    return 0 if passed_all else 1


if __name__ == "__main__":
    sys.exit(main())
