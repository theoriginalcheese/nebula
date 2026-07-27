"""Per-game encoder profiles - spec 7d.

    "Nebula identifies the game before it starts recording, so it can apply
     that game's encoder settings in the same breath."

Stored in `games.json` beside the classification, so a profile syncs across
machines exactly like the classification does:

    "helldivers2.exe": {
        "name": "Helldivers 2", "appid": 553850, "is_game": true,
        "profile": {"enabled": true, "res": "2560x1440", "fps": 60,
                    "encoder": "nvenc_h264", "bitrate_kbps": 18000,
                    "scene": "Game Capture"}
    }

Two rules from the spec are load-bearing and are enforced here rather than
left to the caller:

* **Scope guard.** "resolution, fps, encoder, bitrate, scene. That is the whole
  feature. No audio tracks, no filters, no output paths, no encoder presets -
  those stay in OBS, and Nebula must never silently overwrite settings the user
  changed there." `sanitise()` drops anything else, so a hand-edited games.json
  cannot widen the feature.
* **Never mid-recording.** "Queue it for the next start." `apply()` refuses
  while a recording is active; the monitor calls it before StartRecord.
"""

FIELDS = ("res", "fps", "encoder", "bitrate_kbps", "scene")

ENCODERS = {
    "obs_x264": "x264 (CPU)",
    "nvenc_h264": "NVENC H.264",
    "nvenc_hevc": "NVENC HEVC",
    "jim_nvenc": "NVENC (new)",
    "amd_amf_h264": "AMD H.264",
    "qsv_h264": "QuickSync H.264",
}

BITRATE_RANGE = (1000, 200000)     # kb/s
FPS_CHOICES = (24, 30, 48, 60, 120, 144)


def sanitise(raw):
    """A profile dict with only the five sanctioned keys, or None.

    Anything else in the stored dict is dropped rather than passed on - the
    spec's scope guard has to hold against a hand-edited or synced file, not
    just against this app's own editor.
    """
    if not isinstance(raw, dict):
        return None
    out = {"enabled": bool(raw.get("enabled", True))}
    res = raw.get("res")
    if isinstance(res, str) and "x" in res.lower():
        width, _, height = res.lower().partition("x")
        try:
            out["res"] = f"{int(width)}x{int(height)}"
        except ValueError:
            pass
    for key, caster in (("fps", int), ("bitrate_kbps", int)):
        try:
            if raw.get(key) is not None:
                out[key] = caster(raw[key])
        except (TypeError, ValueError):
            pass
    if out.get("bitrate_kbps") is not None:
        lo, hi = BITRATE_RANGE
        out["bitrate_kbps"] = max(lo, min(hi, out["bitrate_kbps"]))
    if isinstance(raw.get("encoder"), str) and raw["encoder"]:
        out["encoder"] = raw["encoder"]
    if isinstance(raw.get("scene"), str) and raw["scene"]:
        out["scene"] = raw["scene"]
    return out if len(out) > 1 else None


def for_game(classifier, basename):
    """The stored profile for an exe, or None. Falls back to the default."""
    try:
        entry = classifier._data.get("games", {}).get((basename or "").lower())
    except Exception:
        return None
    if not isinstance(entry, dict):
        return None
    profile = sanitise(entry.get("profile"))
    return profile if profile and profile.get("enabled") else None


def save(classifier, basename, profile):
    """Write a profile onto an existing game entry, and persist.

    Uses the classifier's own lock and _save so the write merges with whatever
    another machine has synced, exactly like a classification does.
    """
    basename = (basename or "").lower()
    cleaned = sanitise(profile) if profile else None
    with classifier._lock:
        entry = classifier._data.get("games", {}).get(basename)
        if not isinstance(entry, dict):
            return False
        if cleaned:
            entry["profile"] = cleaned
        else:
            entry.pop("profile", None)
        classifier._save()
    return True


def estimated_gb_per_hour(bitrate_kbps):
    """"Estimated 8.1 GB/h at this bitrate" - shown live in the editor."""
    if not bitrate_kbps:
        return None
    return bitrate_kbps * 1000 * 3600 / 8 / (1024 ** 3)


def summary(profile):
    """The Games pane's profile column: "1440p60 · 18 Mb/s · NVENC"."""
    if not profile:
        return ""
    bits = []
    res, fps = profile.get("res"), profile.get("fps")
    if res:
        height = res.lower().partition("x")[2]
        bits.append(f"{height}p{fps}" if fps else f"{height}p")
    elif fps:
        bits.append(f"{fps} fps")
    if profile.get("bitrate_kbps"):
        bits.append(f"{profile['bitrate_kbps'] / 1000:.0f} Mb/s")
    if profile.get("encoder"):
        bits.append(ENCODERS.get(profile["encoder"], profile["encoder"]))
    if profile.get("scene"):
        bits.append(profile["scene"])
    return "  ·  ".join(bits)


def plan(profile, current_video=None, current_scene=None):
    """The ordered list of OBS calls a profile needs. Empty if nothing changed.

    7d: "Apply sequence - order matters." Resolution and fps go first and
    *only if changed* (SetVideoSettings restarts the video pipeline, so calling
    it needlessly is a visible hitch), then the encoder and bitrate, then the
    scene.

    Returned as data rather than executed so the order is testable without an
    OBS to talk to.
    """
    steps = []
    if not profile:
        return steps

    res, fps = profile.get("res"), profile.get("fps")
    if res or fps:
        want = {}
        if res:
            width, _, height = res.lower().partition("x")
            want["baseWidth"] = want["outputWidth"] = int(width)
            want["baseHeight"] = want["outputHeight"] = int(height)
        if fps:
            want["fpsNumerator"] = int(fps)
            want["fpsDenominator"] = 1
        changed = True
        if current_video:
            changed = any(current_video.get(k) != v for k, v in want.items())
        if changed:
            steps.append(("SetVideoSettings", want))

    if profile.get("encoder"):
        steps.append(("SetProfileParameter",
                      ("SimpleOutput", "RecEncoder", profile["encoder"])))
    if profile.get("bitrate_kbps"):
        steps.append(("SetProfileParameter",
                      ("SimpleOutput", "VBitrate", str(profile["bitrate_kbps"]))))

    scene = profile.get("scene")
    if scene and scene != current_scene:
        steps.append(("SetCurrentProgramScene", scene))
    return steps


def apply(obs, profile, is_recording, on_log=None):
    """Run `plan` against OBS. Refuses while recording.

    "Never apply mid-recording. Queue it for the next start." Changing the
    canvas size or the encoder under a running output is how you get a
    half-corrupt file, so this returns False and the caller tries again at the
    next start rather than forcing it.
    """
    log = on_log or (lambda msg: None)
    if not profile:
        return True
    if is_recording:
        log("[Profile] Not applied - a recording is running. Queued for the next start.")
        return False

    current_video = current_scene = None
    try:
        current_video = obs.get_video_settings()
        current_scene = obs.get_current_program_scene()
    except Exception:
        pass

    steps = plan(profile, current_video, current_scene)
    if not steps:
        return True
    for call, payload in steps:
        try:
            if call == "SetVideoSettings":
                obs.call("SetVideoSettings", payload)
                log(f"[Profile] Canvas {payload.get('baseWidth')}x"
                    f"{payload.get('baseHeight')} @ {payload.get('fpsNumerator')}fps")
            elif call == "SetProfileParameter":
                category, name, value = payload
                obs.set_profile_parameter(category, name, value)
                log(f"[Profile] {name} = {value}")
            elif call == "SetCurrentProgramScene":
                obs.call("SetCurrentProgramScene", {"sceneName": payload})
                log(f"[Profile] Scene -> {payload}")
        except Exception as exc:
            # Bind before logging; `exc` is unbound once the block exits.
            error = str(exc)
            log(f"[Profile] {call} failed: {error}")
            return False
    return True
