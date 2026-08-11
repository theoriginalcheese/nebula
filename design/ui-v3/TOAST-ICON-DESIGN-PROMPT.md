# Claude Design prompt — Nebula toast icons

> Copy everything below the line into Claude Design. This brief is **iconography-first** for the toast capsule; it is not a full product redesign.

**Local refs to scan** (committed beside this file):

- `design/ui-v3/toast-icon-refs/` — lean PNG gallery + `IDENTITY.txt`
- Broader galleries (optional, heavier): `tools/_toast_demo/` in the Nebula repo

---

## Who / what

**Nebula** is a Windows tray app that drives OBS recording per game. The **toast** is the only desktop notification: a **single-slot** capsule, bottom-right, replace-in-place (never a stack). Shipping surface today is **WebView2** (`spike/web/toast.*`) with DWM ~8px outer round — not a true chromakey pill. Tk galleries are the loved *look* reference.

You are designing **icons** (and only light chip/dust notes if needed) that feel expensive, on-brand, and **not AI-generic**.

## Scan these first

Open every PNG under `design/ui-v3/toast-icon-refs/` before drawing. Match that silhouette language: dark Nebula Deep glass, circular chip, soft dust near the chip, thin tinted drain, single-row status copy. Prompt toasts are taller with two pills — icons still live in the same chip.

## Palette (Nebula Deep only)

| Token | Hex | Use on toast |
|-------|-----|----------------|
| Accent | `#8B7CF6` | pause / resume / prompt icons + chip wash |
| Accent text | `#B9AEF9` | icon glyph on dark |
| Ember | `#FF5C7A` | **start / stop / error only** |
| Text | `#F5F3FF` | primary copy |
| Ground / core | `#100D1C` / `#181428` | glass |

No emoji, no second accent hue, no gradient floods. Ember never on pause/resume/prompt/watching.

## Icon set to deliver

Phosphor **Light** conceptually (12–24px). Runtime may map to Segoe Fluent — name Phosphor roles so engineering can map them.

| Role | Tint | Notes |
|------|------|--------|
| **start** | ember | recording live / began |
| **stop** | ember | Fill `ph-square` OK at 9–11px |
| **pause** | accent | |
| **resume** | accent | |
| **error** | ember | |
| **prompt** | accent | decision / “Record again?” — not a literal `?` sticker |
| **watching** | accent / neutral | idle monitoring — **no eye**, no camera iris |

Status dots may use Fill `ph-circle` (6–8px) if you show one; otherwise Light only.

Show each glyph: (1) on the ~28px chip at toast scale, (2) at ~16px so it still reads.

## Aesthetic brief (anti–AI-generic)

- Prefer **machined / transport / signal** metaphors over cute or surveillance.
- One family: same stroke weight, same optical centre in the chip, same corner language.
- Avoid: glossy 3D orbs, neon outlines, duotone stickers, “AI sparkle”, thick rounded-fill icons that fight Light weight.
- Dust constellation stays soft atmosphere — do not replace icons with particle art.
- Prompt icon must still read next to the words “Record again?” without looking like a help tooltip.

## Deliverables

1. **Icon sheet** — all roles above, Light/Fill called out, plus a short **do-not-use** list (especially no eye for watching).
2. **Chip mockups** — each icon on the toast chip (ember chip wash vs accent chip wash as appropriate).
3. **Two toast frames** using the new icons: one ember **start**, one accent **prompt** (with Record / Not now pills). Use the refs for layout; do not invent a grey enclosure.
4. **Watching rationale** — one sentence why the chosen metaphor beats an eye.

## Explicit do not

- No eye / iris / “watching you” for idle monitoring.
- No grey rectangular enclosure around the capsule.
- No ember on pause / resume / prompt / watching.
- No toast stack, avatars, game cover art, or fake metrics.
- No true H/2 pill assumption on WebView — design for DWM ~8px round.

## Success

Icons Anthony would accept as Nebula’s own — quiet, precise, transport-native — that drop into the existing capsule without looking like a stock icon pack or an AI sticker sheet.
