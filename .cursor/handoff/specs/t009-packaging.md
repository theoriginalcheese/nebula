# t009 — Package v4 as a single exe (step 11)

Create `nebula-v4.spec` so `pyinstaller nebula-v4.spec` produces
`dist/Nebula-v4.exe` — a windowed onefile build of `spike/app.py`, alongside the
existing v3 `nebula.spec` (leave that one alone).

## The trap this step exists to avoid

`spike/app.py` resolves its UI like this:

```python
HERE  = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "web", "index.html")
```

Under a frozen onefile build `__file__` resolves inside PyInstaller's temp
extraction dir (`sys._MEIPASS`), which is **deleted on exit**. That is correct
for `web/` — it is a bundled read-only asset — but it is catastrophic for user
data. CLAUDE.md documents this as a live gotcha.

So:

- **`web/` must be bundled** (`index.html`, `app.css`, `app.js`, `tokens.css`,
  `toast.*`, `overlay.*`) and resolved through `RESOURCE_DIR` semantics —
  `sys._MEIPASS` when frozen, the source dir otherwise.
- **User data must never resolve there.** `config.json`, `games.json`,
  `sessions.jsonl`, `logs/`, `offload_queue.json` all go through
  `obsauto/paths.py`'s `APP_DIR` (next to `sys.executable` when frozen).
  Verify nothing in `spike/` writes relative to `__file__`.

`obsauto/paths.py` already implements both. Use it rather than reinventing it.

## Also required

- **`--windowed`** — Nebula runs under `pythonw`, no console.
- Icon `nebula_icon.ico`, bundled as v3 does.
- Hidden imports / data files that static analysis will miss: `pywebview`
  (and its platform backend), `pystray`, `PIL`, `psutil`, `keyboard`,
  `websocket`. Use `collect_data_files` / `collect_submodules` where needed —
  v3's spec already does this for `customtkinter` as a worked example.
- Do **not** bundle `design/ui-v3/` (347 KB mockup + 27 frame PNGs) or
  `shots/`. They are development assets.

## Known frozen-vs-dev trap, do not "fix"

A frozen build and a source run **deliberately do not share data** — the exe
reads `dist/config.json` and writes `dist/logs/`. That is existing, intended
behaviour. When verifying the build, read `dist/logs/obsauto.log`, **not**
`logs/obsauto.log`.

The single-instance mutex is shared, so the exe and a `python spike/app.py` run
cannot both start. That is also intended.

## ⛔ File ownership

**You may ADD** `nebula-v4.spec` and a build note in `V4-GUIDE.md`.
**You may edit** `spike/app.py` **only** if `INDEX` needs to resolve through
`RESOURCE_DIR` — that is the one permitted change, and say so in your report.
Do **not** touch `obsauto/`, `nebula.spec`, or anything under `spike/web/`.

## Definition of done

The standard gate, plus:
- `pyinstaller nebula-v4.spec` completes and produces `dist/Nebula-v4.exe`
- **run the exe**, confirm the window renders with its CSS (a missing `web/`
  bundle shows as an unstyled or blank window — that is the failure mode to
  look for), and screenshot it
- confirm `dist/logs/obsauto.log` is written, and that `dist/config.json` is
  created rather than the repo's being overwritten
- report the exe size
