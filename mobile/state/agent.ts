/**
 * Client for the studio phone agent. Contract: docs/PHONE-AGENT.md.
 *
 * The app is useful with no agent configured at all — every screen already
 * renders an honest empty state — so everything here degrades to "no data"
 * rather than throwing into the UI.
 */
import Constants from 'expo-constants';

import type {
  Clip,
  ClipState,
  ClassifyItem,
  DetectedGame,
  MoonState,
  Offload,
  Peer,
  RecordingStatus,
  StudioState,
} from '@/state/studio';

/** Payload version this client understands. See docs/PHONE-AGENT.md § Versioning. */
export const SUPPORTED_PAYLOAD_VERSION = 1;

export type AgentConfig = { baseUrl: string; token: string };

/**
 * Where the agent lives. Set via app.json `extra`, or an .env consumed by it:
 *
 *   "extra": { "agentUrl": "http://100.x.y.z:8765", "agentToken": "…" }
 *
 * Absent config is the normal case for a fresh checkout, not an error.
 */
export function agentConfig(): AgentConfig | null {
  const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, unknown>;
  const baseUrl = typeof extra.agentUrl === 'string' ? extra.agentUrl.trim() : '';
  const token = typeof extra.agentToken === 'string' ? extra.agentToken.trim() : '';
  if (!baseUrl || !token) return null;
  return { baseUrl: baseUrl.replace(/\/+$/, ''), token };
}

/** What a successful poll contributes to StudioState. */
export type AgentPatch = Pick<
  StudioState,
  | 'recording'
  | 'activity'
  | 'clips'
  | 'moonlight'
  | 'moonlightPaired'
  | 'peers'
  | 'offload'
  | 'detectedGames'
  | 'notGamesCount'
  | 'classifyQueue'
>;

export class AgentError extends Error {}

const REQUEST_TIMEOUT_MS = 6000;

export async function fetchSnapshot(
  config: AgentConfig,
  signal?: AbortSignal,
): Promise<AgentPatch> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  signal?.addEventListener('abort', () => controller.abort());

  let res: Response;
  try {
    res = await fetch(`${config.baseUrl}/v1/snapshot`, {
      headers: { Authorization: `Bearer ${config.token}` },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 401) throw new AgentError('Token rejected by the studio agent.');
  if (!res.ok) throw new AgentError(`Studio agent returned ${res.status}.`);

  const body: unknown = await res.json();
  return parseSnapshot(body);
}

/**
 * Validate and narrow. A payload whose version we do not know is refused
 * outright rather than rendered half-understood.
 */
export function parseSnapshot(body: unknown): AgentPatch {
  if (!isRecord(body)) throw new AgentError('Studio agent sent a malformed payload.');
  if (body.v !== SUPPORTED_PAYLOAD_VERSION) {
    throw new AgentError(
      `Studio agent speaks contract v${String(body.v)}; this app understands v${SUPPORTED_PAYLOAD_VERSION}.`,
    );
  }

  const rec = isRecord(body.recording) ? body.recording : {};

  return {
    recording: {
      status: asRecordingStatus(rec.status),
      encoder: asText(rec.encoder),
      gameTitle: asText(rec.gameTitle),
      sceneName: asText(rec.sceneName),
      elapsedSec: asNumber(rec.elapsedSec),
      fileSizeLabel: asText(rec.fileSizeLabel),
      bitrateLabel: asText(rec.bitrateLabel),
      diskLeftLabel: asText(rec.diskLeftLabel),
      diskWarning: rec.diskWarning === true,
    },
    activity: asArray(body.activity).flatMap(asActivity),
    clips: asArray(body.clips).flatMap(asClip),
    moonlight: asMoonState(body.moonlight),
    moonlightPaired: typeof body.moonlightPaired === 'boolean' ? body.moonlightPaired : null,
    peers: asArray(body.peers).flatMap(asPeer),
    offload: asOffload(body.offload),
    detectedGames: asArray(body.detectedGames).flatMap(asGame),
    notGamesCount: asNumber(body.notGamesCount),
    classifyQueue: asArray(body.classifyQueue).flatMap(asClassifyItem),
  };
}

/* ---------------------------------------------------------------- narrowing */

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

/** Null-preserving: an absent value must stay absent, never become '' or 0. */
function asText(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v : null;
}

function asNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

const RECORDING_STATUSES: RecordingStatus[] = ['idle', 'recording', 'paused', 'stopped'];
function asRecordingStatus(v: unknown): RecordingStatus {
  return RECORDING_STATUSES.includes(v as RecordingStatus) ? (v as RecordingStatus) : 'idle';
}

const MOON_STATES: MoonState[] = ['ready', 'busy', 'live'];
function asMoonState(v: unknown): MoonState {
  return MOON_STATES.includes(v as MoonState) ? (v as MoonState) : 'ready';
}

const CLIP_STATES: ClipState[] = ['recording', 'local', 'offloading', 'on-nas'];
function asClipState(v: unknown): ClipState {
  return CLIP_STATES.includes(v as ClipState) ? (v as ClipState) : 'local';
}

function asActivity(v: unknown): StudioState['activity'] {
  if (!isRecord(v)) return [];
  const label = asText(v.label);
  const id = asText(v.id);
  if (!label || !id) return [];
  const kind = v.kind === 'offline' || v.kind === 'recording' ? v.kind : 'info';
  return [{ id, at: asNumber(v.at), label, kind }];
}

function asClip(v: unknown): Clip[] {
  if (!isRecord(v)) return [];
  const id = asText(v.id);
  const title = asText(v.title);
  if (!id || !title) return [];
  return [
    {
      id,
      title,
      durationLabel: asText(v.durationLabel),
      sizeLabel: asText(v.sizeLabel),
      state: asClipState(v.state),
      startedAt: asNumber(v.startedAt),
      game: asText(v.game),
    },
  ];
}

function asPeer(v: unknown): Peer[] {
  if (!isRecord(v)) return [];
  const id = asText(v.id);
  const name = asText(v.name);
  if (!id || !name) return [];
  return [{ id, name, online: v.online === true, pingMs: asNumber(v.pingMs) }];
}

function asOffload(v: unknown): Offload | null {
  if (!isRecord(v)) return null;
  const total = asNumber(v.total);
  const note = asText(v.note);
  // A job with neither a count nor a note has nothing to say.
  if (!total && !note) return null;
  return {
    done: total ? (asNumber(v.done) ?? 0) : null,
    total: total && total > 0 ? total : null,
    sizeLabel: asText(v.sizeLabel),
    currentFile: asText(v.currentFile),
    throughputLabel: asText(v.throughputLabel),
    note,
  };
}

function asGame(v: unknown): DetectedGame[] {
  if (!isRecord(v)) return [];
  const id = asText(v.id);
  const name = asText(v.name);
  if (!id || !name) return [];
  return [{ id, name, exe: asText(v.exe) ?? '', recording: v.recording !== false }];
}

function asClassifyItem(v: unknown): ClassifyItem[] {
  if (!isRecord(v)) return [];
  const id = asText(v.id);
  const name = asText(v.name);
  if (!id || !name) return [];

  const signals = asArray(v.signals)
    .flatMap((s) => {
      if (!isRecord(s)) return [];
      const text = asText(s.text);
      if (!text) return [];
      return [{ lean: s.lean === 'game' ? ('game' as const) : ('not' as const), text }];
    })
    .slice(0, 5);
  // The card is a fixed five-signal layout; a short list is not renderable.
  if (signals.length !== 5) return [];

  return [
    {
      id,
      name,
      exe: asText(v.exe) ?? '',
      publisher: asText(v.publisher) ?? '',
      // Real icon art needs the executable's icon from the agent; until then
      // the classify card falls back to its generic mark.
      icon: 'sifu',
      tint: 'rgba(139,124,246,.2)',
      confidence: v.confidence === 'high' ? 'high' : 'low',
      signals: signals as ClassifyItem['signals'],
      verdictLabel: asText(v.verdictLabel) ?? '',
      warn: v.warn === true,
    },
  ];
}
