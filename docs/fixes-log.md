# Fixes log

2 October 2026. Four bug-hunt passes tried to break Nebula (find failures, not delete the app). Each one was read-only against the checkout. The failures below are the ones that held up in the code. The fixes are in the same commit as this note.

## Fixed

### Locked offload queue read as empty, then saved
`read_json` treated any `OSError` as "no file" and returned the default. A lock (antivirus, OneDrive) on `offload_queue.json` came back as `[]`, and `_load_queue` wrote that empty list straight back. The queue is the gate in front of a manual delete, so this dropped pending clips from it.

`read_json` now re-raises that error after logging, and leaves the file where it is. Corrupt JSON is still quarantined as `.corrupt`. `_load_queue` and `_load_state` keep the in-memory copy and do not save when the read fails. A later enqueue retries the read first, and still will not write if the file cannot be read — an empty in-memory queue must not be flushed over the real one.

### Clip index wiped or collided
Three separate ways the index lost entries:

- A second `ClipCatalog` (the offloader builds one per finalise; the app keeps another) saved its own memory over the file, dropping whatever the other had just added.
- A corrupt or unreadable `clip_index.json` was treated as an empty index and then overwritten, with no `.corrupt` copy.
- `record_offload` keyed the entry on the source filename. A NAS collision rename (`clip.mkv` and `clip (2).mkv`) stored both under `G/clip.mkv`, so the first recording disappeared from the index and that key opened the second file.

Saves now re-read the file and union it before writing. A delete still passes the key through so it is not read back in. An unreadable index is not saved over. The index key is the destination filename.

### A key filed as both a game and a non-game vanished on pull
If the remote list had `starrail.exe` in both buckets (the old union-merge damage) and this machine had no opinion, absorb stored it in both. The next save then stripped it from each bucket in turn, and it was gone from memory and from disk. Every launch reported it as a new pull.

`merge_classifications` now treats a key in both overlay buckets as damage: games wins, same rule as `_heal`. `absorb` heals after the merge and saves while holding the classifier lock, matching `mark_game`.

### NAS game list with a bad shape was overwritten
`NasGameSync.fetch` turned a non-dict `games` or `non_games` into `{}`. `push` then wrote that back, which is the same "unknown remote treated as empty" failure the GitHub path already refuses. A bad shape now returns `None`, and the push does not write. A missing file is still an empty list, which is a new hub.

### Replays filed outside the recording root, and closed the live session
`ReplayBuffer.target_dir` joined the raw display name. `Honkai: Star Rail` failed with a Windows path error and the file stayed in OBS's output folder. A game named `..` resolved to the parent of the recording root. Recordings already go through `game_folder_under`; replays do too now.

A replay save wrote `rec_stop` with `replay=True`, and both `spans()` and `today()` treated that as the end of the recording. The ribbon closed the session at the replay, the Recorded tile showed the replay's length, and the real stop later counted the same time again. A replay during an open recording is its own clip and does not close the span. A replay with no recording still counts on its own.

### A websocket drop forgot a recording OBS was still making
`_maybe_reconnect` set `_recording_target = None` as soon as the socket dropped. After reconnect, the same game looked new, so the monitor stopped and started again (one session, two files). If you were idle, or the game had closed, `None == None` meant nothing was applied, and OBS kept recording with nothing tracking it.

The target stays put across the blip. On reconnect, `GetRecordStatus` keeps it when `outputActive` is set, and clears it only when OBS is actually not recording. A status call that fails leaves the target and asks again on the next tick, so one error does not split the file and a later "not recording" answer still clears it.

### Editing a hotkey orphaned the replay buffer and the UDP trigger
Settings called `start_replay()` on every hotkey edit. That built a new `ReplayBuffer` with `armed=False` while OBS's buffer was still running. Leaving the game then saw "already disarmed" and never stopped it. The same call built a second `UdpTrigger` without stopping the first, so the new bind failed, and quit only stopped the new one.

Hotkey edits now rebind keys only. `start_hotkeys` stops the existing UDP trigger before opening another. `replay_udp_port` uses that same path. Changing OBS host, port, or password updates the live client (it used to copy those only at startup) and disconnects. If the monitor is already running it reconnects on its own tick, so a port change does not resume a pause and does not open a second websocket. If nothing is connected yet, a reconnect is queued.

### A toast finishing its fade cleared the next prompt
`replace()` stored the new buttons immediately, on the calling thread. The old toast's last fade tick then cleared `_action_callbacks` before it checked whether a newer toast had taken the slot. Record / Not now did nothing, and the prompt's timeout never ran.

Buttons and the timeout are stored in `_replace_gui`, in the same step as the generation bump. `_on_expired` only clears them after that generation is still current.

### Suspend-while-hidden raced the toast reveal
The watch thread and the toast GUI thread both checked `_renderer_asleep` and then set it. A reveal could lose, leaving a blank toast until the next event. `suspend_if_hidden` now runs on the GUI thread, with the replace.

### Recycle Bin could mean a permanent delete
`recyclable()` treated removable drives as having a bin. USB sticks and SD cards do not, and `SHFileOperation` still reports success after a real delete. A file larger than the bin's cap, or a volume with `NukeOnDelete`, does the same under `FOF_NOCONFIRMATION`, with no dialog.

Removable volumes are refused. Before the shell call, the volume's `NukeOnDelete` and `MaxCapacity` are checked and a `RecycleError` is raised instead of deleting. If those registry values are missing, the size check does not guess.

## Not changed

### Each machine's full snapshot wins, so a stale peer reverts the other
`merge_classifications` is documented as "the overlay is the more recent view". Push sends the whole local snapshot as that overlay. Machine B, which has not seen A's promotion (or A's per-game profile), pushes its older entry and the remote goes back. Profiles are replaced whole, so B's entry drops A's `profile`.

That is the current sync rule, not a typo in one function. Fixing it properly means a timestamp per key, or pushing only the keys that changed on this machine. Doing it as a side effect of this pass would change whose classification wins across the desktop and the laptop. Left as-is on purpose.

### A delete in one clip index can be written back by another instance that loaded earlier
Union-on-save keeps entries the saver has never seen, which is the offloader-versus-app bug above. An instance that loaded the index, then saves after a different instance deleted a key, can put that key back. Same-process deletes from the instance that holds the key are fine.
