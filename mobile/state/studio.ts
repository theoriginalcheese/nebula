/**
 * Studio link + recording state.
 * No backend yet — every numeric / title field is null until a real source exists.
 * Never invent demo values (no "Helldivers II", no fake bitrates).
 */

export type ConnectionStatus = 'unknown' | 'online' | 'offline';

export type RecordingStatus = 'idle' | 'recording' | 'paused' | 'stopped';

export type SignalLean = 'game' | 'not';

export type ClassifySignal = {
  /** Which way this individual signal leans — independent of the overall verdict. */
  lean: SignalLean;
  text: string;
};

export type ClassifyIcon = 'sifu' | 'blender' | 'yakuza0';

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
  verdictLabel: string;
  warn: boolean;
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
  };
  activity: Array<{
    id: string;
    at: number | null;
    label: string;
    kind: 'info' | 'offline' | 'recording';
  }>;
  /** Toast payload; null = hidden */
  savedToast: { fileSizeLabel: string | null } | null;
  /**
   * Classify queue. No live classifier backend exists yet, so this starts
   * seeded with the three adversarial fixtures BUILD-SPEC calls out as real
   * QA cases (Sifu / Blender / Yakuza 0) rather than an empty stub — each
   * verdict removes the item for real, same as a live queue would.
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
    tint: 'rgba(90,182,232,.18)',
    confidence: 'high',
    signals: [
      { lean: 'game', text: 'Running fullscreen at native resolution' },
      { lean: 'game', text: 'Xbox controller connected and actively used' },
      { lean: 'game', text: 'GPU load steady at 71%, matches a render loop' },
      { lean: 'game', text: 'Found in Steam library' },
      { lean: 'game', text: 'No title bar or menu chrome' },
    ],
    verdictLabel: 'High confidence, game',
    warn: false,
  },
  {
    id: 'blender',
    name: 'Blender',
    exe: 'blender.exe',
    publisher: 'Blender Foundation',
    icon: 'blender',
    tint: 'rgba(233,184,114,.18)',
    confidence: 'low',
    signals: [
      { lean: 'game', text: 'Running fullscreen — but so is every render preview' },
      { lean: 'not', text: 'Keyboard and mouse only, no controller seen' },
      { lean: 'game', text: 'GPU load spiking high during a viewport render' },
      { lean: 'not', text: 'Not found in any connected store library' },
      { lean: 'not', text: 'Has a menu bar and panel chrome' },
    ],
    verdictLabel: 'Low confidence, not a game',
    warn: true,
  },
  {
    id: 'yakuza0',
    name: 'Yakuza 0',
    exe: 'yakuza0.exe',
    publisher: 'SEGA',
    icon: 'yakuza0',
    tint: 'rgba(212,113,224,.18)',
    confidence: 'low',
    signals: [
      { lean: 'not', text: 'Borderless window, not exclusive fullscreen' },
      { lean: 'not', text: 'Keyboard and mouse only, no controller seen' },
      { lean: 'not', text: 'GPU load low, under 15%' },
      { lean: 'game', text: 'Found in Steam library' },
      { lean: 'game', text: 'No title bar or menu chrome' },
    ],
    verdictLabel: 'Low confidence, game',
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
  },
  activity: [],
  savedToast: null,
  classifyQueue: classifyFixtures,
  decidedToday: 0,
};
