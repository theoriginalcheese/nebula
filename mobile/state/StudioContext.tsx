import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { AccessibilityInfo, Linking } from 'react-native';

import {
  initialStudioState,
  type ClassifyVerdict,
  type ConnectionStatus,
  type StudioState,
} from '@/state/studio';
import { accentPresets, motion, type AccentId } from '@/constants/theme';

/** Moonlight's iOS URL scheme — the app is a launcher, never an embedded decoder. */
const MOONLIGHT_URL = 'moonlight://';

type StudioContextValue = {
  state: StudioState;
  /** Effective ambient-motion multiplier, 0–1. Forced to 0 by OS reduce-motion. */
  motionScale: number;
  /** True when the OS accessibility setting is what is holding motion at zero. */
  reduceMotionFromSystem: boolean;
  accent: AccentId;
  /** Resolved hex + soft pair for the selected accent. */
  accentHex: string;
  accentSoft: string;
  haptics: boolean;
  /** Non-null when the last Moonlight launch attempt could not proceed. */
  moonlightNotice: string | null;
  setConnection: (status: ConnectionStatus) => void;
  setMotionScale: (n: number) => void;
  setAccent: (id: AccentId) => void;
  setHaptics: (on: boolean) => void;
  tryAgain: () => void;
  wakeOverLan: () => void;
  pauseRecording: () => void;
  resumeRecording: () => void;
  stopRecording: () => void;
  recordAgain: () => void;
  dismissToast: () => void;
  launchMoonlight: () => void;
  toggleGameRecording: (id: string) => void;
  decideClassify: (id: string, verdict: ClassifyVerdict) => void;
  skipClassify: (id: string) => void;
};

const StudioContext = createContext<StudioContextValue | null>(null);

export function StudioProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<StudioState>(initialStudioState);
  const [userMotion, setUserMotion] = useState<number>(motion.defaultScale);
  const [reduceMotionFromSystem, setReduceMotionFromSystem] = useState(false);

  /*
    Appearance's Motion slider is the reduce-motion control, but the design
    gives Appearance no entry point — so the OS setting has to reach it on its
    own, or a user who needs reduced motion could never turn it off. The system
    switch wins while it is on; the in-app slider adjusts everything below it.
  */
  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((on) => {
        if (alive) setReduceMotionFromSystem(on);
      })
      .catch(() => {
        // Platform can't report it (web) — leave motion under app control.
      });
    const sub = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      setReduceMotionFromSystem,
    );
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);

  const [moonlightNotice, setMoonlightNotice] = useState<string | null>(null);
  const [accent, setAccent] = useState<AccentId>('violet');
  const [haptics, setHaptics] = useState(true);
  const accentEntry = accentPresets.find((a) => a.id === accent) ?? accentPresets[0];
  const motionScale = reduceMotionFromSystem ? 0 : userMotion;

  const setMotionScale = useCallback((n: number) => {
    setUserMotion(Math.max(0, Math.min(1, n)));
  }, []);

  const setConnection = useCallback((status: ConnectionStatus) => {
    setState((prev) => ({
      ...prev,
      connection: status,
      activity:
        status === 'offline'
          ? [
              {
                id: `offline-${Date.now()}`,
                at: Date.now(),
                label: 'Lost link to Studio PC',
                kind: 'offline' as const,
              },
              ...prev.activity,
            ]
          : prev.activity,
    }));
  }, []);

  const tryAgain = useCallback(() => {
    // No Tailscale probe yet — flip to unknown (honest loading), not fake online.
    setConnection('unknown');
  }, [setConnection]);

  const wakeOverLan = useCallback(() => {
    // WoL needs an always-on tailnet peer to send the magic packet (BUILD-SPEC
    // § Notifications constraint 3). No such peer is wired yet — stub only.
  }, []);

  const pauseRecording = useCallback(() => {
    setState((prev) => {
      if (prev.recording.status !== 'recording') return prev;
      return {
        ...prev,
        recording: { ...prev.recording, status: 'paused' },
      };
    });
  }, []);

  const resumeRecording = useCallback(() => {
    setState((prev) => {
      if (prev.recording.status !== 'paused') return prev;
      return {
        ...prev,
        recording: { ...prev.recording, status: 'recording' },
      };
    });
  }, []);

  const stopRecording = useCallback(() => {
    setState((prev) => {
      if (prev.recording.status !== 'recording' && prev.recording.status !== 'paused') {
        return prev;
      }
      return {
        ...prev,
        recording: { ...prev.recording, status: 'stopped' },
        savedToast: { fileSizeLabel: prev.recording.fileSizeLabel },
      };
    });
  }, []);

  const recordAgain = useCallback(() => {
    // No OBS bridge yet — refuse to invent a recording session.
  }, []);

  const dismissToast = useCallback(() => {
    setState((prev) => ({ ...prev, savedToast: null }));
  }, []);

  const launchMoonlight = useCallback(() => {
    setMoonlightNotice(null);
    Linking.openURL(MOONLIGHT_URL).catch(() => {
      setMoonlightNotice('Moonlight did not open. Install it from the App Store, then try again.');
    });
  }, []);

  const toggleGameRecording = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      detectedGames: prev.detectedGames.map((game) =>
        game.id === id ? { ...game, recording: !game.recording } : game,
      ),
    }));
  }, []);

  const decideClassify = useCallback((id: string, verdict: ClassifyVerdict) => {
    setState((prev) => {
      const item = prev.classifyQueue.find((i) => i.id === id);
      if (!item) return prev;
      return {
        ...prev,
        classifyQueue: prev.classifyQueue.filter((i) => i.id !== id),
        decidedToday: prev.decidedToday + 1,
        // A "game" verdict is what puts a title in the recorded list.
        detectedGames:
          verdict === 'game'
            ? [
                ...prev.detectedGames,
                { id: item.id, name: item.name, exe: item.exe, recording: true },
              ]
            : prev.detectedGames,
      };
    });
  }, []);

  const skipClassify = useCallback((id: string) => {
    setState((prev) => {
      const item = prev.classifyQueue.find((i) => i.id === id);
      if (!item) return prev;
      return {
        ...prev,
        classifyQueue: [...prev.classifyQueue.filter((i) => i.id !== id), item],
      };
    });
  }, []);

  const value = useMemo(
    () => ({
      state,
      motionScale,
      reduceMotionFromSystem,
      accent,
      accentHex: accentEntry.hex,
      accentSoft: accentEntry.soft,
      haptics,
      moonlightNotice,
      setConnection,
      setMotionScale,
      setAccent,
      setHaptics,
      tryAgain,
      wakeOverLan,
      pauseRecording,
      resumeRecording,
      stopRecording,
      recordAgain,
      dismissToast,
      launchMoonlight,
      toggleGameRecording,
      decideClassify,
      skipClassify,
    }),
    [
      state,
      motionScale,
      reduceMotionFromSystem,
      accent,
      accentEntry,
      haptics,
      moonlightNotice,
      setConnection,
      setMotionScale,
      setAccent,
      setHaptics,
      tryAgain,
      wakeOverLan,
      pauseRecording,
      resumeRecording,
      stopRecording,
      recordAgain,
      dismissToast,
      launchMoonlight,
      toggleGameRecording,
      decideClassify,
      skipClassify,
    ],
  );

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}

export function useStudio() {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error('useStudio must be used within StudioProvider');
  return ctx;
}
