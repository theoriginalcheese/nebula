# t004 — Command palette (7e) and per-game profiles (7d), UI only

The Python for both is **done and tested**. This is the interface over it.
Do not reimplement matching, ranking or validation — call the Api.

## ⛔ File ownership

**You may edit only:** `spike/web/app.js`, `spike/web/app.css`,
`spike/web/index.html`.
**Do NOT touch** `spike/app.py`, `spike/host.py`, `spike/windows.py`,
`spike/web/toast.*`, `spike/web/overlay.*` — another agent is in those now.

Need a new Api method? Say so in your report; do not add it yourself.

## Api already available (verified working)

```js
await pywebview.api.palette_search(query)
// -> {groups:[{group, rows:[{label, hint, spans:[int], action:[kind,arg]}]}], total}
await pywebview.api.palette_run(action)        // action is the row's [kind, arg]
// -> {ok, goto?, select?}

await pywebview.api.profile_get(basename)
// -> {ok, basename, profile, summary, gb_per_hour}
await pywebview.api.profile_save(basename, raw)
// -> {ok, profile, summary} | {ok:false, error}
```

Measured live: `palette_search('clip')` → `[('Actions',1)]`;
`palette_search('')` → `[('Actions',5),('Games',4),('Settings',1)]`, total 11.

## 7e — the palette, frame 7e

- Opens on the configured hotkey (`config.toggle`/`palette_hotkey`, currently
  `ctrl+k`) **and** from a rail affordance. The hotkey itself is bound host-side
  in a later step — for now wire the in-window keydown so it works when focused,
  and report that the global binding is outstanding.
- **`spans` are matched character positions in `label`** — bold exactly those
  characters, nothing else. They are positions, not ranges.
- **An empty query is not an empty list** — it offers suggestions, grouped. The
  Api already does this; render what it returns.
- Group order comes from the Api response; do not re-sort it.
- Arrow keys walk the flattened rows across groups; Enter runs the selected row
  via `palette_run`; Escape closes.
- Footer reads "N of M" using `total`.
- **No destructive rows.** `palette.Row` cannot carry one by construction, so
  none will arrive — do not add a delete affordance of your own.
- `{ok:true, goto:'clips'}` means switch pane; `select` names a game to focus.

## 7d — per-game profiles, frame 7d

- Lives in the **Games** pane: selecting a game reveals its profile.
- Fields come from whatever `profile_get` returns; show `summary` and, when
  present, `gb_per_hour` as the human consequence of the setting.
- **Write on blur**, same as Settings already does — call `profile_save`.
- On `{ok:false}` show the error inline against the field and keep the old
  value. Never swallow it.
- A game with no profile shows the honest empty state, not invented defaults.

## Rules

- `transform` and `opacity` only. Pane-change rise is `--pane-change-rise` /
  `--pane-change-ms` / `--ease`.
- No hand-typed hex, radii, durations or easings — tokens only.
- Two-layer cards; inner radius = outer − padding.
- No fabricated numbers.

## Definition of done

The standard gate, plus:
- `python tools/gpu_ab.py` — visible must not regress beyond ~26% (baseline 24.1%)
- screenshots of the palette open and of a game's profile, **opened and described**
- confirm empty-query suggestions render, and that bolding matches `spans`
