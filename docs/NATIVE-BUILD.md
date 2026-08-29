# Native iOS build

Everything here is configured and validated. The one missing piece is an
**Apple Developer Program membership ($99/yr)** — without it Apple will not
issue the provisioning profile EAS needs, and there is no way around that on
Windows.

## Why the paid account is unavoidable

Installing a native iOS app needs a signed `.ipa`. Producing one needs either
a Mac (Xcode) or a cloud builder. EAS is the cloud builder and its iOS device
builds require ad-hoc provisioning, which Apple only issues to enrolled
accounts — a free "personal team" cannot create one.

Sideloading tools (AltStore, Sideloadly, iSign Loader) do run on Windows with
a free Apple ID, but they *sign an existing `.ipa`*; they cannot produce one.
The chain breaks at the first step. Free-ID signing also expires every 7 days.

## Once you have the account

```
cd mobile
npx eas-cli login                 # your Expo account
npx eas-cli build:configure       # links the project, writes the EAS project id
npx eas-cli build --platform ios --profile device
```

EAS prompts for the Apple ID, registers the device, and generates the
certificate and profile for you. When it finishes it prints a QR code and an
install URL — open that on the iPhone and it installs like any app. No Mac
involved at any point.

`device` is the profile to use: internal distribution, Release configuration,
not a simulator build.

## What is already done

| Piece | Where | Note |
|---|---|---|
| Bundle id | `app.json` → `ios.bundleIdentifier` | `app.nebula.mobile` |
| Build number | `app.json` → `ios.buildNumber` | bump per upload, or use the `production` profile's `autoIncrement` |
| Cleartext HTTP allowed | `app.json` → `ios.infoPlist` | see below |
| Export compliance | `app.json` → `ITSAppUsesNonExemptEncryption: false` | skips the question on every build |
| Agent URL | `eas.json` → `build.base.env` | absolute, no token |
| Icons / splash | `app.json`, `assets/images/` | already used by the web build |

`npx expo-doctor` passes 18/18 and `npx expo config --type introspect`
resolves without errors, so the configuration itself is known good.

### The App Transport Security exception

iOS blocks plain HTTP by default, and the studio agent speaks HTTP over the
tailnet. Rather than disabling ATS wholesale with `NSAllowsArbitraryLoads`,
the exception is scoped to this tailnet's MagicDNS domain:

```json
"NSExceptionDomains": {
  "tail25e601.ts.net": {
    "NSExceptionAllowsInsecureHTTPLoads": true,
    "NSIncludesSubdomains": true
  }
}
```

Nothing else in the app may make a cleartext request. If the tailnet is ever
renamed this must change with it.

### Why it points at port 8766, not 8765

`eas.json` sets `EXPO_PUBLIC_AGENT_URL` to the **app server**
(`http://alien-pc.tail25e601.ts.net:8766`), not the agent itself. Two reasons:

1. **No token in the binary.** `EXPO_PUBLIC_*` values are inlined at build
   time, so pointing at the agent's own port would bake the bearer token into
   the app. The app server already holds it.
2. **The headless fallback comes for free.** That server answers `/v1` from the
   agent when Nebula is running and from `obsauto/phone_state.py` when it is
   not, so the native app works after a reboot with nobody logged in — same as
   the home-screen build.

MagicDNS is used rather than `100.90.134.9` because the name is stable across
address changes, and because an ATS exception can be scoped to a domain but
not to a bare IP.

## Prerequisite on the phone

Tailscale must be connected, exactly as for the web build. The app has no
route to the studio otherwise, and will show its honest "can't reach Studio
PC" state.

## What the paid account also unlocks

Push notifications, and therefore the whole `#f-notify` frame in the design —
Live Activities showing recording status on the lock screen, updated by push
rather than by the phone asking. That work is unstarted; see
`docs/PHONE-AGENT.md` § Why polling, not push.
