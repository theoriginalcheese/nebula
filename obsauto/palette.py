"""Command palette matching and ranking - spec 7e.

    "Fuzzy match across four sources at once, grouped, keyboard-first."

The matching half lives here, apart from the window, because it is the part
with rules worth testing:

    Match     subsequence, case-insensitive, bold the hits
    Ranking   prefix > word-start > anywhere, then recency
    Sources   Actions → Games → Recent clips → Settings
    Limits    max 5 rows per group, 12 rows total

`spans` comes back with every matched character position so the view can bold
exactly the hits rather than guessing at them.

One rule is enforced here rather than left to the callers: **destructive rows
never appear**. "no delete, no cull" - a fuzzy search that can delete something
two keystrokes after a typo is a trap, so `Row` has no way to be destructive
and the builders simply don't offer those actions.
"""

GROUP_ORDER = ("Actions", "Games", "Recent clips", "Settings")
MAX_PER_GROUP = 5
MAX_ROWS = 12

# Ranking tiers - lower sorts first. "prefix > word-start > anywhere".
RANK_PREFIX = 0
RANK_WORD_START = 1
RANK_ANYWHERE = 2


class Row:
    """One palette entry. `recency` breaks ties within a rank tier."""

    __slots__ = ("group", "label", "hint", "action", "recency", "spans", "rank")

    def __init__(self, group, label, action, hint="", recency=0.0):
        self.group = group
        self.label = label
        self.hint = hint
        self.action = action
        self.recency = recency
        self.spans = ()
        self.rank = RANK_ANYWHERE

    def __repr__(self):
        return f"<Row {self.group}:{self.label!r}>"


WORD_BREAKS = " -_/\\.:—·"


def _greedy(q, t, start):
    positions = []
    for char in q:
        found = t.find(char, start)
        if found < 0:
            return None
        positions.append(found)
        start = found + 1
    return tuple(positions)


def subsequence(query, text):
    """Positions of `query`'s characters in `text`, or None.

    Case-insensitive, and word-aware. Plain greedy left-to-right gets "rec"
    against "Start recording" wrong: it takes the r of "Start", then ec from
    "recording", so the match is scattered across two words and ranks as a
    mid-string hit rather than the word-start one it plainly is. Each word
    boundary is tried as an anchor and the tightest result wins, which fixes
    both the ranking and the characters that get bolded.
    """
    if not query:
        return ()
    q, t = query.lower(), text.lower()
    candidates = []
    best = _greedy(q, t, 0)
    if best is None:
        return None                      # not present at all, at any anchor
    candidates.append(best)
    for i, char in enumerate(t):
        if char != q[0]:
            continue
        if i == 0 or t[i - 1] in WORD_BREAKS:
            found = _greedy(q, t, i)
            if found is not None:
                candidates.append(found)
    # Tightest run wins; ties go to the earliest.
    return min(candidates, key=lambda p: (p[-1] - p[0] - (len(p) - 1), p[0]))


def rank_of(query, text, positions):
    """Which tier a match lands in: prefix, word-start, or anywhere."""
    if not positions:
        return RANK_ANYWHERE
    first = positions[0]
    lowered = text.lower()
    if lowered.startswith(query.lower()):
        return RANK_PREFIX
    if first == 0 or text[first - 1] in " -_/\\.":
        return RANK_WORD_START
    return RANK_ANYWHERE


def _tightness(positions):
    """How clustered the matched characters are - a tiebreak inside a tier.

    "rec" against "Start recording" beats "rec" against "Reconnect interval"
    only if something prefers contiguous runs; without this the order inside a
    tier is arbitrary and the list jitters as you type.
    """
    if len(positions) < 2:
        return 0
    return positions[-1] - positions[0] - (len(positions) - 1)


def search(rows, query, max_per_group=MAX_PER_GROUP, max_rows=MAX_ROWS):
    """Filter, rank and group. Returns [(group, [Row, ...]), ...].

    An empty query is not an empty list - "Empty query - suggestions, not a
    blank list" - so everything is offered, still grouped and still capped,
    ordered by recency.
    """
    matched = []
    for row in rows:
        if not query:
            row.spans = ()
            row.rank = RANK_ANYWHERE
            matched.append(row)
            continue
        positions = subsequence(query, row.label)
        target = row.label
        if positions is None and row.hint:
            positions = subsequence(query, row.hint)
            target = row.hint
            if positions is not None:
                positions = ()      # don't bold the hint; it isn't the label
        if positions is None:
            continue
        row.spans = positions if target is row.label else ()
        row.rank = rank_of(query, row.label, row.spans)
        matched.append(row)

    matched.sort(key=lambda r: (
        r.rank,
        _tightness(r.spans),
        -r.recency,
        len(r.label),
        r.label.lower(),
    ))

    grouped, counts, total = [], {}, 0
    for name in GROUP_ORDER:
        bucket = []
        for row in matched:
            if row.group != name:
                continue
            if counts.get(name, 0) >= max_per_group or total >= max_rows:
                break
            bucket.append(row)
            counts[name] = counts.get(name, 0) + 1
            total += 1
        if bucket:
            grouped.append((name, bucket))
    return grouped


def flatten(grouped):
    """Every row in display order - what the arrow keys walk."""
    return [row for _group, rows in grouped for row in rows]


def count_all(rows, query):
    """How many rows match in total, for the "5 of 23 results" footer."""
    if not query:
        return len(rows)
    return sum(1 for r in rows
               if subsequence(query, r.label) is not None
               or (r.hint and subsequence(query, r.hint) is not None))
