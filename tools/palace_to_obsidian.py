"""Render the MemPalace into an Obsidian vault so you can *see* it.

    python tools/palace_to_obsidian.py --dry-run
    python tools/palace_to_obsidian.py --room ui
    python tools/palace_to_obsidian.py                 # everything

Why this is an export and not a merge
-------------------------------------
MemPalace stores drawers in ChromaDB - a sqlite file plus vectors. Obsidian
reads markdown files off disk. There is no format they share, so they cannot be
"merged": one of them has to be projected into the other's shape.

Projecting palace -> markdown is the safe direction. The palace stays the source
of truth, the vault becomes a **read-only view** you can browse, search and open
in Graph View. Nothing here writes back, so a note you edit in Obsidian will be
overwritten on the next run - by design. Edit memories through MemPalace.

(The other direction already exists and is how most of these drawers got there:
`mempalace mine` reads files *into* the palace.)

One note per SOURCE, not per drawer
-----------------------------------
Measured on this palace: 4,005 drawers, of which **4,001 were auto-mined from
36 chat transcripts** and only 4 were authored. A single conversation had been
chopped into 859 drawers.

Exporting one note per drawer therefore produced 4,005 nodes representing 36
conversations - a hairball that shows the chunking, not the knowledge. So the
default unit is now the **source file**: one note per conversation, with its
drawers as sections inside it. ~40 notes instead of 4,005.

Authored drawers (anything not mined) still get their own note, because those
are curated and each one is a distinct thought.

    <vault>/<out>/
        Palace.md              index: every room, with counts
        rooms/<room>.md        one note per room
        sources/<name>.md      one note per mined conversation
        notes/<title>.md       one note per authored drawer

`--per-drawer` restores the old exploded behaviour if you ever want it.
"""
import argparse
import os
import re
import sqlite3
import sys
from collections import defaultdict

DB = os.path.expanduser("~/.mempalace/palace/chroma.sqlite3")
DEFAULT_VAULT = os.path.expanduser(r"~/Claude Memories/claude-memory")
DEFAULT_OUT = "palace"

CHUNK_RE = re.compile(r"_chunk_\d+$")
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


UUIDISH = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-", re.I)


def note_name(drawer_id, source_file, body=""):
    """A note name a human can scan in a sidebar.

    Three fallbacks, in order of usefulness:

      1. the drawer's opening line - what it is actually about
      2. the source filename - useful for files, useless for transcripts
      3. the drawer id - always unique, never informative

    Most drawers here were mined from session transcripts whose filenames are
    UUIDs, so preferring the source would fill the vault with
    `006a69c7-e5e8-4606-... 00a56b96`, which is worse than no export at all.
    """
    short = drawer_id.rsplit("_", 1)[-1][:8]

    first = ""
    for line in (body or "").splitlines():
        line = line.strip().lstrip("#-*> ").strip()
        if len(line) > 12:
            first = line
            break
    if first:
        return safe("%s %s" % (first[:60].rstrip(" .,:;"), short))

    stem = os.path.splitext(os.path.basename(source_file or ""))[0]
    if stem and not UUIDISH.match(stem):
        return safe("%s %s" % (stem, short))
    return safe(drawer_id)


def safe(name, limit=80):
    """A filename Obsidian and Windows will both accept."""
    name = UNSAFE.sub("-", str(name)).strip(". ")
    return (name[:limit] or "untitled").rstrip(". ")


def load(db_path):
    """Every drawer, with its chunks stitched back together in order."""
    uri = "file:%s?mode=ro" % db_path.replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)

    meta = defaultdict(dict)
    for rid, key, sval, ival in con.execute(
            "SELECT id, key, string_value, int_value FROM embedding_metadata"):
        meta[rid][key] = sval if sval is not None else ival

    rows = con.execute("SELECT id, embedding_id FROM embeddings").fetchall()
    con.close()

    drawers = defaultdict(lambda: {"chunks": [], "meta": {}})
    for rid, emb_id in rows:
        m = meta.get(rid, {})
        drawer_id = CHUNK_RE.sub("", emb_id or "")
        if not drawer_id:
            continue
        d = drawers[drawer_id]
        idx = m.get("chunk_index") or 0
        d["chunks"].append((idx, m.get("chroma:document") or ""))
        # Chunks of one drawer share their metadata; last non-empty wins.
        for k in ("wing", "room", "source_file", "filed_at", "added_by", "hall"):
            if m.get(k):
                d["meta"][k] = m[k]
    for d in drawers.values():
        d["chunks"].sort(key=lambda c: c[0])
    return drawers


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Only rewrite when the content actually differs, so Obsidian's file
    # watcher and git both stay quiet on a no-op run.
    if os.path.isfile(path):
        try:
            if open(path, encoding="utf-8").read() == text:
                return False
        except OSError:
            pass
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="subfolder inside the vault (default: palace)")
    ap.add_argument("--room", help="export one room only")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.db):
        raise SystemExit("palace not found: %s" % a.db)
    if not os.path.isdir(a.vault):
        raise SystemExit("vault not found: %s" % a.vault)

    drawers = load(a.db)
    by_room = defaultdict(list)
    for did, d in drawers.items():
        room = d["meta"].get("room") or "unfiled"
        if a.room and room != a.room:
            continue
        by_room[room].append((did, d))

    total = sum(len(v) for v in by_room.values())
    root = os.path.join(a.vault, a.out)

    print("palace : %s" % a.db)
    print("vault  : %s" % root)
    print("rooms  : %s" % ", ".join("%s(%d)" % (r, len(v))
                                    for r, v in sorted(by_room.items())))
    print("drawers: %d" % total)
    if a.dry_run:
        print("\n(dry run - nothing written)")
        return 0

    written = 0
    MINED = "mempalace"

    # --- authored drawers: one note each (curated, each a distinct thought)
    authored = defaultdict(list)
    mined = defaultdict(lambda: defaultdict(list))     # room -> source -> [(id, meta, body)]

    for room, items in sorted(by_room.items()):
        for did, d in items:
            m = d["meta"]
            body = "\n\n".join(c for _, c in d["chunks"]).strip()
            src = m.get("source_file") or ""
            if (m.get("added_by") or "") == MINED:
                mined[room][src].append((did, m, body))
            else:
                authored[room].append((did, m, body, src))

    for room, items in sorted(authored.items()):
        for did, m, body, src in items:
            name = note_name(did, src, body)
            head = ["---", "drawer: %s" % did, "wing: %s" % (m.get("wing") or ""),
                    "room: %s" % room, "filed: %s" % (m.get("filed_at") or ""),
                    "added_by: %s" % (m.get("added_by") or ""),
                    "source: %s" % src.replace("\\", "/"),
                    "tags: [palace, authored, %s]" % room, "---", "",
                    "Room: [[%s]]" % room, "", "---", ""]
            written += write(os.path.join(root, "notes", safe(room), "%s.md" % name),
                             "\n".join(head) + "\n" + body + "\n")

    # --- mined drawers: one note per conversation, drawers as sections
    for room, per_src in sorted(mined.items()):
        for src, rows in sorted(per_src.items()):
            stem = os.path.splitext(os.path.basename(src))[0] or "unknown"
            name = safe("%s (%d)" % (stem, len(rows)))
            filed = sorted((r[1].get("filed_at") or "") for r in rows)
            head = ["---", "wing: %s" % (rows[0][1].get("wing") or ""),
                    "room: %s" % room,
                    "source: %s" % src.replace("\\", "/"),
                    "drawers: %d" % len(rows),
                    "first_filed: %s" % (filed[0] if filed else ""),
                    "tags: [palace, mined, %s]" % room, "---", "",
                    "# %s" % stem, "",
                    "%d drawer%s mined from this transcript. Room: [[%s]]"
                    % (len(rows), "" if len(rows) == 1 else "s", room), "",
                    "> Auto-mined chunks of one conversation, not %d separate "
                    "memories." % len(rows), ""]
            parts = []
            for did, m, body in rows:
                short = did.rsplit("_", 1)[-1][:8]
                parts.append("\n---\n\n### %s\n\n%s" % (short, body))
            written += write(os.path.join(root, "sources", safe(room), "%s.md" % name),
                             "\n".join(head) + "".join(parts) + "\n")

    # --- one note per room
    for room, items in sorted(by_room.items()):
        lines = ["---", "tags: [palace, room]", "---", "",
                 "# %s" % room, "",
                 "%d drawer%s. Part of [[Palace]]." % (len(items),
                                                       "" if len(items) == 1 else "s"),
                 ""]
        auth = [r for r in items if (r[1]["meta"].get("added_by") or "") != "mempalace"]
        if auth:
            lines += ["## Authored", ""]
            for did, d in auth:
                b = "\n\n".join(c for _, c in d["chunks"])
                lines.append("- [[%s]]" % note_name(did, d["meta"].get("source_file") or "", b))
            lines.append("")

        per_src = defaultdict(int)
        for did, d in items:
            if (d["meta"].get("added_by") or "") == "mempalace":
                per_src[d["meta"].get("source_file") or "(no source)"] += 1
        if per_src:
            lines += ["## Mined conversations", ""]
            for src, n in sorted(per_src.items(), key=lambda kv: -kv[1]):
                stem = os.path.splitext(os.path.basename(src))[0] or "unknown"
                lines.append("- [[%s]] — %d drawers" % (safe("%s (%d)" % (stem, n)), n))
            lines.append("")
        written += write(os.path.join(root, "rooms", "%s.md" % safe(room)),
                         "\n".join(lines) + "\n")

    # --- the index
    idx = ["---", "tags: [palace]", "---", "", "# Palace", "",
           "A read-only view of MemPalace, exported by "
           "`tools/palace_to_obsidian.py`.", "",
           "**Edits here are overwritten.** The palace is the source of truth; "
           "this is a window onto it.", "",
           "| Room | Drawers |", "|---|---|"]
    for room, items in sorted(by_room.items(), key=lambda kv: -len(kv[1])):
        idx.append("| [[%s]] | %d |" % (safe(room), len(items)))
    idx += ["", "Total: **%d** drawers across **%d** rooms." % (total, len(by_room))]
    written += write(os.path.join(root, "Palace.md"), "\n".join(idx) + "\n")

    print("\nwrote/updated %d file(s)" % written)
    print("Open the vault in Obsidian and start at Palace.md, or press Ctrl+G "
          "for Graph View.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
