"""Shared game list parsing, the corner update prompt, and checked exe names.

    python tests/test_shared_update.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import classifier as classifier_mod
from obsauto.gamesync import (
    fetch_public_list, names_only, parse_public_list, shared_upload_overlay,
)
from obsauto.classifier import merge_classifications
from obsauto.updater import offer_from_check

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


raw = json.dumps({
    "games": {
        "Terraria.exe": {"display_name": "Terraria"},
        "not-an-exe": {"display_name": "Nope"},
        "../evil.exe": {"display_name": "Evil"},
    },
    "non_games": {"chrome.exe": True, "terraria.exe": True, "notes.txt": True},
    "extra": {"token": "should be dropped"},
})
parsed = parse_public_list(raw)
check("parse keeps a real exe",
      parsed and parsed["games"].get("terraria.exe", {}).get("display_name") == "Terraria")
check("parse drops a non-exe key", "not-an-exe" not in (parsed or {}).get("games", {}))
check("parse drops a path", "../evil.exe" not in (parsed or {}).get("games", {}))
check("a game is not also a non-game",
      "terraria.exe" not in (parsed or {}).get("non_games", {}))
check("parse keeps chrome as a non-game",
      (parsed or {}).get("non_games", {}).get("chrome.exe") is True)
check("junk json is ignored", parse_public_list("nope") is None)
check("plain http is refused", fetch_public_list("http://example.com/list.json") is None)
check("blank url is refused", fetch_public_list("") is None)

repo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "classifications.json")
with open(repo, encoding="utf-8") as fh:
    seeded = parse_public_list(fh.read())
check("seed file parses", seeded is not None and len(seeded["games"]) >= 40)
check("seed includes a checked exe",
      seeded and seeded["games"].get("cs2.exe", {}).get("display_name") == "Counter-Strike 2")
check("guessed tf2.exe is not in the seed",
      seeded and "tf2.exe" not in seeded["games"])

check("no offer when current", offer_from_check({"status": "current"}) is None)
dirty = offer_from_check({
    "status": "update", "kind": "source", "dirty": True, "head": "abc",
})
check("dirty source checkout is not prompted", dirty is None)
offer = offer_from_check({
    "status": "update", "kind": "release",
    "release": {"tag": "v9.0.0"}, "message": "A newer build is on GitHub.",
}, "")
check("release offer carries its tag", offer and offer["tag"] == "v9.0.0")
check("dismissed tag stays hidden",
      offer_from_check({
          "status": "update", "kind": "release", "release": {"tag": "v9.0.0"},
      }, "v9.0.0") is None)
source_offer = offer_from_check({
    "status": "update", "kind": "source", "dirty": False, "local_ahead": 0,
    "head": "local", "remote_head": "abc123",
}, "")
check("source prompt tracks origin, not this PC",
      source_offer and source_offer["tag"] == "source:abc123")
check("unpushed commits are not prompted",
      offer_from_check({
          "status": "update", "kind": "source", "dirty": False,
          "local_ahead": 2, "remote_head": "abc123",
      }, "") is None)
stripped = names_only({
    "games": {"Terraria.exe": {
        "display_name": "Terraria", "appid": 105600,
        "profile": {"fps": 60},
    }},
    "non_games": {"chrome.exe": {"note": "personal"}},
})
check("upload shape is names only",
      stripped["games"]["terraria.exe"] == {"display_name": "Terraria"}
      and stripped["non_games"] == {"chrome.exe": True}
      and "profile" not in json.dumps(stripped))

remote_games = {"games": {"foo.exe": {"display_name": "Foo"}}, "non_games": {}}
overlay = shared_upload_overlay({
    "games": {"bar.exe": {"display_name": "Bar"}},
    "non_games": {"foo.exe": True, "chrome.exe": True},
}, remote_games)
check("upload keeps a local non-game that the list does not call a game",
      overlay["non_games"] == {"chrome.exe": True})
merged = merge_classifications(remote_games, overlay)
check("upload does not demote someone else's game",
      "foo.exe" in merged["games"] and "foo.exe" not in merged["non_games"])
check("upload still adds this PC's game",
      merged["games"]["bar.exe"]["display_name"] == "Bar")

old = classifier_mod.DATA_FILE
tmp = tempfile.mkdtemp()
classifier_mod.DATA_FILE = os.path.join(tmp, "games.json")
try:
    clf = classifier_mod.Classifier()
    kind, name = clf.classify("", "Terraria.exe")
    check("builtin name classifies as a game",
          kind == "game" and name == "Terraria", "%s %s" % (kind, name))
    clf.mark_non_game("terraria.exe")
    kind2, _name2 = clf.classify("", "Terraria.exe")
    check("a local not-a-game wins over the builtin list", kind2 == "non_game", kind2)
    clf.absorb({
        "games": {"terraria.exe": {"display_name": "Terraria", "source": "shared"}},
        "non_games": {},
    })
    kind3, _name3 = clf.classify("", "Terraria.exe")
    check("a local not-a-game survives the public pull", kind3 == "non_game", kind3)
finally:
    classifier_mod.DATA_FILE = old

check("llm inventions stayed out",
      "garrysvietnam.exe" not in classifier_mod.KNOWN_GAMES
      and "reddead2.exe" not in classifier_mod.KNOWN_GAMES
      and "minecraft.exe" not in classifier_mod.KNOWN_GAMES)

failed = [name for name, ok, _detail in results if not ok]
for name, ok, detail in results:
    print("%s  %s%s" % ("ok" if ok else "FAIL", name, ("  " + detail) if detail and not ok else ""))
print("%d/%d" % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)
