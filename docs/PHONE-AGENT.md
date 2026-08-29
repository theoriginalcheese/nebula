# Phone agent contract (v1)

The wire contract between desktop Nebula on the studio PC and the iOS
companion in `mobile/`. One endpoint, read-only, tailnet-only.

## Why it looks like this

`spike/app.py`'s `Api.snapshot()` already computes every section the phone
needs — `obs`, `hero`, `activity`, `ribbon`, `clips_panel`, `forecast`,
`games`, `remote` — and it is fault-isolated per section, so one hung
subsystem cannot blank the rest. The agent is therefore a **projection** of
that payload into the phone's own shape, not a second source of truth. Adding
a stat to the phone means projecting an existing field, not writing new
collection logic.

## Transport

| Property | Value |
|---|---|
| Protocol | HTTP/1.1, JSON, no TLS |
| Bind | The machine's **Tailscale IPv4 only** — never `0.0.0.0`, never the LAN address |
| Port | `8765` (override: `phone_agent_port`) |
| Auth | `Authorization: Bearer <token>` on every request, `phone_agent_token` in `config.json` |
| Enabled | Off unless `phone_agent_enabled` is true; the module is imported lazily so it stays off the startup import chain |

No TLS because the tailnet already provides encryption and device identity —
the same reasoning that gates the other admin UIs. Binding to the Tailscale
interface means the socket does not exist on the home LAN at all, so a guest
on the WiFi cannot reach it even with the token.

### Why polling, not push

BUILD-SPEC § Notifications constraint 2 calls for push, because the phone
cannot poll a sleeping PC. **Push needs a paid Apple developer account**, and
this project uses a free one — no APNs, no push-updated Live Activities, no
TestFlight, and 7-day build expiry. So v1 polls while the app is foregrounded
and shows honest "last seen" staleness otherwise, which is sufficient for the
product's stated job ("the two minutes away from the machine").

The contract is shaped so a relay can be added later without the phone
changing: an always-on tailnet peer (the NAS) can cache the last snapshot and
serve the same payload at the same path when the studio PC is asleep. The
phone would only learn a new base URL.

## Endpoints

### `GET /v1/health`

Cheap reachability probe. `{"ok": true, "v": 1, "host": "<hostname>"}`.

### `GET /v1/snapshot`

The whole phone payload. Mirrors `StudioState` in `mobile/state/studio.ts`
field-for-field, minus the two client-local fields (`savedToast`,
`decidedToday`).

```jsonc
{
  "v": 1,
  "at": 1787866182.88,          // server unix time, for staleness display
  "connection": "online",        // always "online" if you got a response
  "recording": {
    "status": "idle",            // idle | recording | paused | stopped
    "encoder": null,             // "1080p60 · NVENC"
    "gameTitle": null,
    "sceneName": null,
    "elapsedSec": null,
    "fileSizeLabel": null,       // pre-formatted; the desktop owns formatting
    "bitrateLabel": null,
    "diskLeftLabel": null,       // "4d left"
    "diskWarning": false         // true only when the forecast is genuinely low
  },
  "activity": [
    { "id": "…", "at": 1787866182.88, "label": "…", "kind": "info" }
  ],
  "clips": [
    { "id": "…", "title": "…", "durationLabel": null, "sizeLabel": "3.10 GB",
      "state": "on-nas", "startedAt": 1787866182.88, "game": "…" }
  ],
  "moonlight": "ready",          // ready | busy | live
  "moonlightPaired": null,       // null = not reported, never assumed true
  "peers": [
    { "id": "nas-vault", "name": "nas-vault", "online": true, "pingMs": 7 }
  ],
  "offload": null,               // or { done, total, sizeLabel, currentFile, throughputLabel }
  "detectedGames": [
    { "id": "…", "name": "…", "exe": "…", "recording": true }
  ],
  "notGamesCount": null,
  "classifyQueue": [ /* ClassifyItem, see mobile/state/studio.ts */ ]
}
```

## Rules

1. **Null, never invented.** Every scalar is nullable and the phone renders
   `—` for null. The agent must never substitute a plausible value for a
   missing one — that is the same rule the desktop's `_remote` already
   follows ("honest status only, nothing fabricated").
2. **Formatting belongs to the desktop.** `fileSizeLabel`, `diskLeftLabel`,
   `bitrateLabel` and `durationLabel` arrive pre-formatted so the two clients
   cannot drift into rendering the same number differently. Raw numbers are
   sent only where the phone does arithmetic (`elapsedSec`, `pingMs`,
   `offload.done`/`total`).
3. **Read-only.** v1 exposes no mutating endpoint. A stale phone view issuing
   Stop would end a live recording, which is precisely what the sacred-footage
   rule exists to prevent. Commands arrive in v2, reversible ones first
   (pause/resume, per-game record toggles, classify verdicts); Stop last, if
   at all.
4. **No footage paths.** The agent reads catalogue metadata only. It never
   opens, moves, or deletes a recording, and never returns an absolute path
   into `Z:\OBS`, `D:\OBS TEMP`, or any other footage location.
5. **Never fatal to the app.** The server runs on a daemon thread and every
   handler is wrapped. A failure in the agent must degrade to a 500 for the
   phone, never take down desktop Nebula.

## Versioning

`v` is the payload version. The phone refuses a payload whose `v` it does not
know rather than rendering a half-understood shape. Additive fields do not
bump `v`; removing or retyping a field does.

## Setup

In `config.json` on the studio PC:

```json
{
  "phone_agent_enabled": true,
  "phone_agent_token": "<a long random string>",
  "phone_agent_port": 8765
}
```

Point the phone at `http://<tailscale-ip-of-studio-pc>:8765` with the same
token. `tailscale ip -4` prints the address.
