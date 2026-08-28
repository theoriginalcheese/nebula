import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

import {
  initialStudioState,
  type ConnectionStatus,
  type StudioState,
} from '@/state/studio';
import { motion } from '@/constants/theme';

type StudioContextValue = {
  state: StudioState;
  motionScale: number;
  setConnection: (status: ConnectionStatus) => void;
  setMotionScale: (n: number) => void;
  tryAgain: () => void;
  wakeOverLan: () => void;
  pauseRecording: () => void;
  resumeRecording: () => void;
  stopRecording: () => void;
  recordAgain: () => void;
  dismissToast: () => void;
  decideClassify: (id: string) => void;
  skipClassify: (id: string) => void;
};

const StudioContext = createContext<StudioContextValue | null>(null);

export function StudioProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<StudioState>(initialStudioState);
  const [motionScale, setMotionScaleState] = useState<number>(motion.defaultScale);
  const setMotionScale = useCallback((n: number) => {
    setMotionScaleState(Math.max(0, Math.min(1, n)));
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
    // TODO: WoL via always-on tailnet peer — stub only.
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

  const decideClassify = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      classifyQueue: prev.classifyQueue.filter((item) => item.id !== id),
      decidedToday: prev.decidedToday + 1,
    }));
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
      setConnection,
      setMotionScale,
      tryAgain,
      wakeOverLan,
      pauseRecording,
      resumeRecording,
      stopRecording,
      recordAgain,
      dismissToast,
      decideClassify,
      skipClassify,
    }),
    [
      state,
      motionScale,
      setConnection,
      setMotionScale,
      tryAgain,
      wakeOverLan,
      pauseRecording,
      resumeRecording,
      stopRecording,
      recordAgain,
      dismissToast,
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
