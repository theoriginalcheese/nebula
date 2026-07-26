# Nebula UI v3 — local design package

Imported from Claude Design project `19d87879-67c8-4a4e-8eb1-d4fbd327a23a`,
file **Nebula UI Mockups v3.dc.html**. No further DesignSync / `claude_design` MCP
import is required unless the remote mockup changes.

## Files

| Path | Role |
|------|------|
| `Nebula UI Mockups v3.dc.html` | Interactive mockup — open in a browser |
| `support.js` | Design-canvas runtime (generated; don’t edit) |
| `_ds/nocturne-…/styles.css` | House DS tokens — **v3 does not use these** |
| `_ds/nocturne-…/_ds_bundle.js` | Empty component bundle |
| `BUILD-SPEC.md` | § 05 contract — **authority** |
| `FRAMES.md` | Frames 2a–2k notes |
| `NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md` | Paste/continue prompt for Claude Code |

## View the mockup

Open `Nebula UI Mockups v3.dc.html` in Chrome/Edge. It loads Geist and Phosphor from
CDNs, so you need network.

## Claude Code — Downloads copy

```bat
copy "%USERPROFILE%\nebula\design\ui-v3\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md" "%USERPROFILE%\Downloads\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md"
```

Adjust the source path if your clone is not `C:\Users\antho\nebula`. Then open that
Downloads file in Claude Code and work against the repo.

## Implemented where

- Tokens / geometry / hero enum → `obsauto/design_v3.py`
- UI → `obsauto/gui.py`
- Brief → `CURSOR-HANDOFF.md` / `CURSOR-PROMPT.md`
