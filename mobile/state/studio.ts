/**
 * Studio link + recording state.
 * No backend yet — every numeric / title field is null or empty until a real
 * source exists. Never invent demo values (no "Helldivers II", no fake
 * bitrates, no fake peers). The only seeded data in this file is the classify
 * queue, which BUILD-SPEC explicitly designates as adversarial QA fixtures.
 */

export type ConnectionStatus = 'unknown' | 'online' | 'offline';

export type RecordingStatus = 'idle' | 'recording' | 'paused' | 'stopped';

/** Moonlight launcher states — f-remote hero orb. */
export type MoonState = 'ready' | 'busy' | 'live';

export type SignalLean = 'game' | 'not';

export type ClassifySignal = {
  /** Which way this individual signal leans — independent of the overall verdict. */
  lean: SignalLean;
  text: string;
};

export type ClassifyIcon = 'sifu' | 'blender' | 'yakuza0';

export type ClassifyVerdict = 'game' | 'not';

export type ClassifyItem = {
  id: string;
  name: string;
  exe: string;
  publisher: string;
  icon: ClassifyIcon;
  tint: string;
  confidence: 'high' | 'low';
  /** fullscreen state, input device, GPU load, store-library membership, window-chrome */
  signals: [ClassifySignal, ClassifySignal, ClassifySignal, ClassifySignal, ClassifySignal];
  /** Short verdict phrase, rendered as "{verdictLabel}, so Nebula is asking instead of guessing." */
  verdictLabel: string;
  warn: boolean;
};

/** Where a finished clip currently lives — drives the trailing row icon on f-clips. */
export type ClipState = 'recording' | 'local' | 'offloading' | 'on-nas';

export type Clip = {
  id: string;
  title: string;
  /** Pre-formatted duration, e.g. "42:08". Null while still unknown. */
  durationLabel: string | null;
  sizeLabel: string | null;
  state: ClipState;
  /** ms epoch the clip started; groups the day sections. */
  startedAt: number | null;
  /** Game name used by the filter chip row. */
  game: string | null;
};

export type Peer = {
  id: string;
  name: string;
  online: boolean;
  /** Round-trip ms; null when unknown or offline. */
  pingMs: number | null;
};

export type Offload = {
  /**
   * Files already moved, and the batch size. Both null when the desktop only
   * reports a human note — the progress bar renders only when these are real,
   * never with an invented fill. See docs/PHONE-AGENT.md.
   */
  done: number | null;
  total: number | null;
  /** Total size of the batch, pre-formatted. */
  sizeLabel: string | null;
  /** Current file line, e.g. "Factorio replay". */
  currentFile: string | null;
  throughputLabel: string | null;
  /** Human sentence from the desktop, e.g. "3 clips queued · over LAN". */
  note: string | null;
};

export type DetectedGame = {
  id: string;
  name: string;
  exe: string;
  /** Whether Nebula records this title. Mirrors the f-games row toggle. */
  recording: boolean;
};

export type StudioState = {
  connection: ConnectionStatus;
  /** Last time we successfully reached the studio PC (ms epoch), or null. */
  lastSeenAt: number | null;
  /** Only set when we know recording was not active at disconnect. */
  recordingSafeOnDisconnect: boolean | null;
  recording: {
    status: RecordingStatus;
    /** Null = unknown / no data source yet */
    encoder: string | null;
    gameTitle: string | null;
    sceneName: string | null;
    /** Elapsed seconds while recording/paused; null if unknown */
    elapsedSec: number | null;
    fileSizeLabel: string | null;
    bitrateLabel: string | null;
    diskLeftLabel: string | null;
    /** True only when the agent reports the disk countdown is in warning range. */
    diskWarning: boolean;
  };
  activity: Array<{
    id: string;
    at: number | null;
    label: string;
    kind: 'info' | 'offline' | 'recording';
  }>;
  /** Toast payload; null = hidden */
  savedToast: { fileSizeLabel: string | null } | null;

  /** f-clips — empty until the agent syncs clip metadata. */
  clips: Clip[];

  /** f-remote — Moonlight launcher state, tailnet peers, NAS offload job. */
  moonlight: MoonState;
  /** Whether the Moonlight host has been reported paired. Null = unknown. */
  moonlightPaired: boolean | null;
  peers: Peer[];
  offload: Offload | null;

  /** f-games — executables the detector has seen. Empty until reported. */
  detectedGames: DetectedGame[];
  /** Count of executables already ruled "not a game". Null = unknown. */
  notGamesCount: number | null;

  /**
   * Classify queue. No live classifier backend exists yet, so this starts
   * seeded with the three adversarial fixtures BUILD-SPEC calls out as real
   * QA cases (Sifu / Blender / Yakuza 0) rather than an empty stub — each
   * verdict removes the item for real, same as a live queue would.
   * Copy is transcribed verbatim from the QUEUE constant in Nebula Mobile.dc.html.
   */
  classifyQueue: ClassifyItem[];
  decidedToday: number;
};

const classifyFixtures: ClassifyItem[] = [
  {
    id: 'sifu',
    name: 'Sifu',
    exe: 'sifu.exe',
    publisher: 'Sloclap',
    icon: 'sifu',
    tint: 'rgba(90,182,232,.2)',
    confidence: 'high',
    signals: [
      { lean: 'game', text: 'Exclusive fullscreen, 2h 14m' },
      { lean: 'game', text: 'Gamepad, 11.4k events' },
      { lean: 'game', text: 'GPU 94% sustained' },
      { lean: 'game', text: 'In your Steam library' },
      { lean: 'game', text: 'No window chrome' },
    ],
    verdictLabel: 'Looks like a game',
    warn: false,
  },
  {
    id: 'blender',
    name: 'Blender',
    exe: 'blender.exe',
    publisher: 'Blender Foundation',
    icon: 'blender',
    tint: 'rgba(233,184,114,.2)',
    confidence: 'low',
    signals: [
      { lean: 'game', text: 'Fullscreen, 41m' },
      { lean: 'not', text: 'Keyboard and mouse only' },
      { lean: 'game', text: 'GPU 88% sustained, bursty' },
      { lean: 'not', text: 'Not in any store library' },
      { lean: 'not', text: 'Menu bar and toolbars' },
    ],
    verdictLabel: 'Trips every heuristic',
    warn: true,
  },
  {
    id: 'yakuza0',
    name: 'Yakuza 0',
    exe: 'yakuza0.exe',
    publisher: 'Ryu Ga Gotoku',
    icon: 'yakuza0',
    tint: 'rgba(212,113,224,.2)',
    confidence: 'low',
    signals: [
      { lean: 'not', text: 'Borderless window, 1600x900' },
      { lean: 'not', text: 'Keyboard only' },
      { lean: 'not', text: 'GPU 41% sustained' },
      { lean: 'game', text: 'In your Steam library' },
      { lean: 'game', text: 'Borderless, chrome hidden' },
    ],
    verdictLabel: 'Hides from the heuristics',
    warn: true,
  },
];

/** Initial honest empty state — connection unknown, no fabricated stats. */
export const initialStudioState: StudioState = {
  connection: 'unknown',
  lastSeenAt: null,
  recordingSafeOnDisconnect: null,
  recording: {
    status: 'idle',
    encoder: null,
    gameTitle: null,
    sceneName: null,
    elapsedSec: null,
    fileSizeLabel: null,
    bitrateLabel: null,
    diskLeftLabel: null,
    diskWarning: false,
  },
  activity: [],
  savedToast: null,
  clips: [],
  moonlight: 'ready',
  moonlightPaired: null,
  peers: [],
  offload: null,
  detectedGames: [],
  notGamesCount: null,
  classifyQueue: classifyFixtures,
  decidedToday: 0,
};

/** Day-grouped clips for the f-clips list. Empty in, empty out. */
export type ClipDay = {
  key: string;
  /** "Today" / "Yesterday" / "12 Aug" */
  label: string;
  clips: Clip[];
  /** Pre-formatted "6h 12m · 11 clips" style meta, or null when unknown. */
  meta: string | null;
};

function dayKey(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function dayLabel(ms: number): string {
  const d = new Date(ms);
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86400000);
  if (dayKey(ms) === dayKey(today.getTime())) return 'Today';
  if (dayKey(ms) === dayKey(yesterday.getTime())) return 'Yesterday';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

export function groupClipsByDay(clips: Clip[]): ClipDay[] {
  const buckets = new Map<string, Clip[]>();
  const undated: Clip[] = [];

  for (const clip of clips) {
    if (clip.startedAt == null) {
      undated.push(clip);
      continue;
    }
    const key = dayKey(clip.startedAt);
    const existing = buckets.get(key);
    if (existing) existing.push(clip);
    else buckets.set(key, [clip]);
  }

  const days: ClipDay[] = [];
  for (const [key, group] of buckets) {
    const first = group[0];
    days.push({
      key,
      label: first.startedAt != null ? dayLabel(first.startedAt) : '—',
      clips: group,
      meta: `${group.length} clip${group.length === 1 ? '' : 's'}`,
    });
  }
  days.sort((a, b) => (b.clips[0].startedAt ?? 0) - (a.clips[0].startedAt ?? 0));

  if (undated.length > 0) {
    days.push({ key: 'undated', label: 'Undated', clips: undated, meta: null });
  }
  return days;
}
