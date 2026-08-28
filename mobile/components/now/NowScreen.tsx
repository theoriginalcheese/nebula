import { useEffect, useRef } from 'react';
import {
  Alert,
  Animated,
  Easing,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { ScreenHeader } from '@/components/ScreenHeader';
import { AmbientBackdrop } from '@/components/ui/AmbientBackdrop';
import { DeadMark } from '@/components/ui/DeadMark';
import { DustParticles } from '@/components/ui/DustParticles';
import { Eyebrow } from '@/components/ui/Eyebrow';
import { RecordingArcMark } from '@/components/ui/RecordingArcMark';
import { colors, fonts, radii } from '@/constants/theme';
import { useStudio } from '@/state/StudioContext';

const TAB_CLEAR = 110;

function formatClock(sec: number | null): string {
  if (sec == null) return '—:—:—';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':');
}

function formatActivityTime(at: number | null): string {
  if (at == null) return '—';
  const d = new Date(at);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function formatLastSeen(at: number | null): string {
  if (at == null) return 'last seen —';
  const d = new Date(at);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const mins = Math.max(0, Math.round((Date.now() - at) / 60000));
  return `last seen ${hh}:${mm} · ${mins}m ago`;
}

type Chip = {
  tint: string;
  fill: string;
  text: string;
  label: string;
};

function chipFor(status: string): Chip {
  switch (status) {
    case 'recording':
      return {
        tint: '#F5A623',
        fill: 'rgba(245,166,35,.14)',
        text: '#F5A623',
        label: 'Recording',
      };
    case 'paused':
      return {
        tint: '#8B7CF6',
        fill: 'rgba(139,124,246,.14)',
        text: '#B9AEF9',
        label: 'Paused',
      };
    case 'stopped':
      return {
        tint: '#B7B1D0',
        fill: 'rgba(245,243,255,.06)',
        text: '#B7B1D0',
        label: 'Saved',
      };
    default:
      return {
        tint: '#736BA4',
        fill: 'rgba(245,243,255,.06)',
        text: '#736BA4',
        label: 'Idle',
      };
  }
}

function StopHalo({ active, motionScale }: { active: boolean; motionScale: number }) {
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!active || motionScale <= 0) {
      pulse.stopAnimation();
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 1200,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 1200,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [active, motionScale, pulse]);

  if (!active) return null;
  const opacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0.7] });
  return (
    <Animated.View
      pointerEvents="none"
      style={[
        StyleSheet.absoluteFillObject,
        {
          margin: -5,
          borderRadius: 999,
          backgroundColor: 'rgba(255,92,122,0.3)',
          opacity,
        },
      ]}
    />
  );
}

export function NowScreen() {
  const insets = useSafeAreaInsets();
  const {
    state,
    motionScale,
    tryAgain,
    wakeOverLan,
    pauseRecording,
    resumeRecording,
    stopRecording,
    recordAgain,
    dismissToast,
  } = useStudio();

  const offline = state.connection === 'offline';
  const rec = state.recording;
  const isRec = rec.status === 'recording';
  const isPaused = rec.status === 'paused';
  const isStopped = rec.status === 'stopped';
  const isActive = isRec || isPaused;
  const chip = chipFor(rec.status);

  useEffect(() => {
    if (!state.savedToast) return;
    const t = setTimeout(dismissToast, 3200);
    return () => clearTimeout(t);
  }, [state.savedToast, dismissToast]);

  const confirmStop = () => {
    Alert.alert('Stop recording?', 'This ends the current session on the studio PC.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Stop', style: 'destructive', onPress: stopRecording },
    ]);
  };

  if (offline) {
    return (
      <View style={styles.screen}>
        <AmbientBackdrop variant="offline" />
        <View style={{ paddingTop: insets.top }}>
          <ScreenHeader
            variant="nebula-wordmark"
            subtitle="No route"
            subtitleDanger
            onlineDot="offline"
            mutedWordmark
          />
        </View>
        <ScrollView
          contentContainerStyle={[
            styles.body,
            { paddingBottom: TAB_CLEAR + insets.bottom },
          ]}
          showsVerticalScrollIndicator={false}>
          <LinearGradient
            colors={['rgba(255,92,122,0.06)', 'rgba(245,243,255,0.015)']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.offlineOuter}>
            <View style={styles.offlineInner}>
              <DeadMark size={96} motionScale={motionScale} />
              <View style={{ gap: 8, alignItems: 'center' }}>
                <Text style={styles.offlineTitle}>Can&apos;t reach Studio PC</Text>
                <Text style={styles.offlineBody}>
                  Tailscale says the machine is offline.
                  {state.recordingSafeOnDisconnect === true
                    ? ' Nothing was recording when the link dropped, so no clip is at risk.'
                    : ''}
                </Text>
              </View>
              <View style={styles.lastSeenPill}>
                <Text style={styles.lastSeenText}>{formatLastSeen(state.lastSeenAt)}</Text>
              </View>
            </View>
          </LinearGradient>

          <Pressable
            onPress={tryAgain}
            style={({ pressed }) => [styles.ctaPrimary, pressed && { transform: [{ scale: 0.97 }] }]}>
            <Svg width={17} height={17} viewBox="0 0 24 24" fill="none">
              <Path
                d="M20 12a8 8 0 1 1-2.6-5.9M20 4.4V10h-5.6"
                stroke={colors.textPrimary}
                strokeWidth={1.7}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </Svg>
            <Text style={styles.ctaPrimaryLabel}>Try again</Text>
          </Pressable>

          <Pressable
            onPress={wakeOverLan}
            style={({ pressed }) => [styles.ctaSecondary, pressed && { transform: [{ scale: 0.97 }] }]}>
            <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
              <Path
                d="M12 3.4v7.8M7.8 6.4a7.4 7.4 0 1 0 8.4 0"
                stroke={colors.textSecondary}
                strokeWidth={1.7}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </Svg>
            <Text style={styles.ctaSecondaryLabel}>Wake over LAN</Text>
          </Pressable>

          <ActivitySection items={state.activity} />
        </ScrollView>
      </View>
    );
  }

  const navDot =
    state.connection === 'online' ? 'online' : state.connection === 'offline' ? 'offline' : 'unknown';
  const navSubtitle =
    state.connection === 'offline'
      ? 'No route'
      : state.connection === 'online'
        ? 'Studio PC'
        : 'Studio PC';

  return (
    <View style={styles.screen}>
      <AmbientBackdrop variant="now" />
      <View style={{ paddingTop: insets.top }}>
        <ScreenHeader
          variant="nebula-wordmark"
          subtitle={navSubtitle}
          onlineDot={navDot}
        />
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: TAB_CLEAR + insets.bottom }]}
        showsVerticalScrollIndicator={false}>
        <LinearGradient
          colors={['rgba(245,166,35,0.07)', 'rgba(245,243,255,0.02)']}
          start={{ x: 0.15, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.recOuter}>
          <View style={styles.recInner}>
            <View style={styles.statusRow}>
              <View style={styles.statusLeft}>
                <View style={styles.chipWrap}>
                  {isActive ? (
                    <DustParticles
                      mode="burst"
                      colour={chip.tint}
                      motionScale={motionScale}
                      size={28}
                    />
                  ) : null}
                  <View style={[styles.chipCore, { backgroundColor: chip.fill }]}>
                    {isRec ? (
                      <Svg width={13} height={13} viewBox="0 0 24 24">
                        <Circle cx="12" cy="12" r="6.2" fill="#F5A623" />
                      </Svg>
                    ) : isPaused ? (
                      <Svg width={13} height={13} viewBox="0 0 24 24" fill="none">
                        <Path
                          d="M9.5 6.5v11M14.5 6.5v11"
                          stroke="#B9AEF9"
                          strokeWidth={2.2}
                          strokeLinecap="round"
                        />
                      </Svg>
                    ) : isStopped ? (
                      <Svg width={13} height={13} viewBox="0 0 24 24" fill="none">
                        <Path
                          d="M20 6.5 9.5 17 4 11.5"
                          stroke="#B7B1D0"
                          strokeWidth={2.2}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </Svg>
                    ) : (
                      <View style={[styles.idleDot, { backgroundColor: chip.tint }]} />
                    )}
                  </View>
                </View>
                <Eyebrow color={chip.text}>{chip.label}</Eyebrow>
              </View>
              <Text style={styles.encoder}>{rec.encoder ?? '—'}</Text>
            </View>

            <View style={styles.titleRow}>
                <View style={{ flex: 1, gap: 5, minWidth: 0, minHeight: 48 }}>
                  <Text style={styles.gameTitle} numberOfLines={2}>
                    {rec.gameTitle ?? '—'}
                  </Text>
                  <Text style={styles.sceneLine}>
                    Scene ·{' '}
                    <Text style={{ color: colors.textSecondary }}>{rec.sceneName ?? '—'}</Text>
                  </Text>
                </View>
              <RecordingArcMark spinning={isRec && motionScale > 0} size={52} />
            </View>

            <Text style={styles.clock}>{formatClock(rec.elapsedSec)}</Text>

            <LinearGradient
              colors={['transparent', 'rgba(245,243,255,0.12)', 'rgba(245,243,255,0.12)', 'transparent']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={styles.divider}
            />

            <View style={styles.statsRow}>
              {(
                [
                  ['File', rec.fileSizeLabel, colors.textPrimary],
                  ['Bitrate', rec.bitrateLabel, colors.textPrimary],
                  ['Disk', rec.diskLeftLabel, colors.accentAmber],
                ] as const
              ).map(([label, value, colour]) => (
                <View key={label} style={styles.statCell}>
                  <Eyebrow tracking="tight">{label}</Eyebrow>
                  <Text style={[styles.statValue, { color: colour }]}>{value ?? '—'}</Text>
                </View>
              ))}
            </View>
          </View>
        </LinearGradient>

        {isActive ? (
          <View style={styles.transport}>
            <View style={styles.transportItem}>
              <Pressable
                onPress={isRec ? pauseRecording : resumeRecording}
                style={({ pressed }) => [
                  styles.pauseBtn,
                  pressed && { transform: [{ scale: 0.94 }] },
                ]}>
                {isRec ? (
                  <Svg width={22} height={22} viewBox="0 0 24 24">
                    <Rect x="7.6" y="5.4" width="3.4" height="13.2" rx="1.7" fill={colors.textPrimary} />
                    <Rect x="13" y="5.4" width="3.4" height="13.2" rx="1.7" fill={colors.textPrimary} />
                  </Svg>
                ) : (
                  <Svg width={22} height={22} viewBox="0 0 24 24">
                    <Path d="M8.4 5.4 18.6 12 8.4 18.6z" fill={colors.textPrimary} />
                  </Svg>
                )}
              </Pressable>
              <Text style={styles.pauseLabel}>{isRec ? 'Pause' : 'Resume'}</Text>
            </View>

            <View style={styles.transportItem}>
              <View style={styles.stopWrap}>
                <StopHalo active={isRec} motionScale={motionScale} />
                <Pressable
                  onPress={confirmStop}
                  style={({ pressed }) => [
                    styles.stopBtn,
                    pressed && { transform: [{ scale: 0.94 }] },
                  ]}>
                  <Svg width={26} height={26} viewBox="0 0 24 24">
                    <Rect x="6.6" y="6.6" width="10.8" height="10.8" rx="2.8" fill="#FFE1E7" />
                  </Svg>
                </Pressable>
              </View>
              <Text style={styles.stopLabel}>Stop</Text>
            </View>
          </View>
        ) : (
          <View style={styles.recordAgainWrap}>
            <View style={styles.stopWrap}>
              <View style={styles.recordHalo} />
              <Pressable
                onPress={recordAgain}
                style={({ pressed }) => [
                  styles.recordAgainBtn,
                  pressed && { transform: [{ scale: 0.94 }] },
                ]}>
                <Svg width={26} height={26} viewBox="0 0 24 24">
                  <Circle cx="12" cy="12" r="6.6" fill={colors.goldText} />
                </Svg>
              </Pressable>
            </View>
            <Text style={styles.recordAgainLabel}>
              {isStopped ? 'Record again' : 'Record'}
            </Text>
          </View>
        )}

        <ActivitySection items={state.activity} />
      </ScrollView>

      {state.savedToast ? (
        <View style={[styles.toast, { bottom: TAB_CLEAR + insets.bottom - 16 }]}>
          <View style={styles.toastIcon}>
            <Svg width={14} height={14} viewBox="0 0 24 24" fill="none">
              <Path
                d="M20 6 9 17l-5-5"
                stroke="#C9BFFF"
                strokeWidth={1.8}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </Svg>
          </View>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={styles.toastTitle}>Recording saved</Text>
            <Text style={styles.toastMeta}>{state.savedToast.fileSizeLabel ?? '—'}</Text>
          </View>
        </View>
      ) : null}
    </View>
  );
}

function ActivitySection({
  items,
}: {
  items: Array<{ id: string; at: number | null; label: string; kind: string }>;
}) {
  return (
    <View style={{ gap: 11, paddingTop: 2 }}>
      <Eyebrow>Activity</Eyebrow>
      {items.length === 0 ? (
        <Text style={styles.activityEmpty}>No activity yet</Text>
      ) : (
        <View style={{ gap: 11 }}>
          {items.map((item) => {
            const offline = item.kind === 'offline';
            const recording = item.kind === 'recording';
            return (
              <View key={item.id} style={styles.activityRow}>
                <View
                  style={[
                    styles.activityIcon,
                    {
                      backgroundColor: offline
                        ? 'rgba(255,92,122,.13)'
                        : recording
                          ? 'rgba(245,166,35,.13)'
                          : 'rgba(139,124,246,.13)',
                    },
                  ]}>
                  {offline ? (
                    <Svg width={11} height={11} viewBox="0 0 24 24" fill="none">
                      <Path
                        d="M5 5l14 14M5 19 19 5"
                        stroke="#FF9DB0"
                        strokeWidth={2}
                        strokeLinecap="round"
                      />
                    </Svg>
                  ) : recording ? (
                    <Svg width={11} height={11} viewBox="0 0 24 24">
                      <Circle cx="12" cy="12" r="6.2" fill="#F5A623" />
                    </Svg>
                  ) : (
                    <Svg width={11} height={11} viewBox="0 0 24 24" fill="none">
                      <Path
                        d="M4 8.5h11l-3-3M20 15.5H9l3 3"
                        stroke="#B9AEF9"
                        strokeWidth={2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </Svg>
                  )}
                </View>
                <Text style={[styles.activityLabel, offline && { color: '#FF9DB0' }]}>
                  {item.label}
                </Text>
                <Text style={styles.activityTime}>{formatActivityTime(item.at)}</Text>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bgScreen },
  body: { paddingHorizontal: 16, gap: 14, paddingTop: 4 },
  recOuter: {
    borderRadius: 26,
    borderWidth: 1,
    borderColor: 'rgba(245,166,35,.2)',
    padding: 5,
  },
  recInner: {
    backgroundColor: colors.bgCard,
    borderRadius: 21,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(245,243,255,.08)',
    paddingTop: 18,
    paddingHorizontal: 18,
    paddingBottom: 20,
    gap: 15,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    minHeight: 30,
  },
  statusLeft: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  chipWrap: { width: 28, height: 28 },
  chipCore: {
    position: 'absolute',
    zIndex: 1,
    width: 28,
    height: 28,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  idleDot: { width: 8, height: 8, borderRadius: 999 },
  encoder: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.textLabel,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 14,
  },
  gameTitle: {
    fontSize: 23,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.506,
    lineHeight: 26.5,
    color: colors.textPrimary,
  },
  sceneLine: {
    fontSize: 11.5,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  clock: {
    fontFamily: fonts.mono,
    fontSize: 44,
    fontWeight: '400',
    letterSpacing: -1.32,
    lineHeight: 44,
    color: colors.textPrimary,
    fontVariant: ['tabular-nums'],
  },
  divider: { height: 1, width: '100%' },
  statsRow: { flexDirection: 'row', gap: 10 },
  statCell: { flex: 1, gap: 4 },
  statValue: {
    fontFamily: fonts.mono,
    fontSize: 14,
    fontVariant: ['tabular-nums'],
  },
  transport: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'center',
    gap: 38,
    paddingVertical: 14,
    paddingBottom: 6,
  },
  transportItem: { alignItems: 'center', gap: 11 },
  pauseBtn: {
    width: 60,
    height: 60,
    borderRadius: 999,
    backgroundColor: 'rgba(245,243,255,.05)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.13)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  pauseLabel: {
    fontSize: 11,
    fontFamily: fonts.ui,
    letterSpacing: 0.22,
    color: colors.textSecondary,
  },
  stopWrap: { width: 76, height: 76 },
  stopBtn: {
    position: 'absolute',
    zIndex: 1,
    width: 76,
    height: 76,
    borderRadius: 999,
    backgroundColor: 'rgba(255,92,122,.2)',
    borderWidth: 1,
    borderColor: 'rgba(255,197,209,.32)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stopLabel: {
    fontSize: 11,
    fontFamily: fonts.uiSemi,
    letterSpacing: 0.22,
    color: '#FFB3C2',
  },
  recordAgainWrap: {
    alignItems: 'center',
    gap: 11,
    paddingVertical: 14,
    paddingBottom: 6,
  },
  recordHalo: {
    ...StyleSheet.absoluteFillObject,
    margin: -5,
    borderRadius: 999,
    backgroundColor: 'rgba(245,166,35,0.24)',
  },
  recordAgainBtn: {
    position: 'absolute',
    zIndex: 1,
    width: 76,
    height: 76,
    borderRadius: 999,
    backgroundColor: 'rgba(245,166,35,.2)',
    borderWidth: 1,
    borderColor: 'rgba(255,232,188,.32)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  recordAgainLabel: {
    fontSize: 11,
    fontFamily: fonts.uiSemi,
    letterSpacing: 0.22,
    color: colors.accentAmber,
  },
  offlineOuter: {
    borderRadius: 26,
    borderWidth: 1,
    borderColor: 'rgba(255,92,122,.22)',
    padding: 5,
  },
  offlineInner: {
    backgroundColor: colors.bgCard,
    borderRadius: 21,
    paddingVertical: 26,
    paddingHorizontal: 20,
    alignItems: 'center',
    gap: 16,
  },
  offlineTitle: {
    fontSize: 21,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.42,
    lineHeight: 25,
    color: colors.textPrimary,
    textAlign: 'center',
  },
  offlineBody: {
    fontSize: 13,
    lineHeight: 21,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
    maxWidth: 270,
    textAlign: 'center',
  },
  lastSeenPill: {
    paddingVertical: 7,
    paddingHorizontal: 14,
    borderRadius: radii.pill,
    backgroundColor: 'rgba(245,243,255,.04)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.07)',
  },
  lastSeenText: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.textMuted,
  },
  ctaPrimary: {
    height: 56,
    borderRadius: radii.pill,
    backgroundColor: 'rgba(139,124,246,.32)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.09)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  ctaPrimaryLabel: {
    fontSize: 14.5,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.145,
    color: colors.textPrimary,
  },
  ctaSecondary: {
    height: 52,
    borderRadius: radii.pill,
    backgroundColor: 'rgba(245,243,255,.045)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.09)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 9,
  },
  ctaSecondaryLabel: {
    fontSize: 14,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
  },
  activityEmpty: {
    fontSize: 12,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  activityRow: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  activityIcon: {
    width: 22,
    height: 22,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  activityLabel: {
    flex: 1,
    fontSize: 12,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
  },
  activityTime: {
    fontFamily: fonts.mono,
    fontSize: 10,
    color: colors.textLabel,
  },
  toast: {
    position: 'absolute',
    left: 20,
    right: 20,
    zIndex: 5,
    borderRadius: 18,
    backgroundColor: 'rgba(10,8,18,.92)',
    borderWidth: 1,
    borderColor: 'rgba(139,124,246,.34)',
    paddingVertical: 13,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  toastIcon: {
    width: 30,
    height: 30,
    borderRadius: 999,
    backgroundColor: 'rgba(139,124,246,.18)',
    borderWidth: 1,
    borderColor: 'rgba(139,124,246,.4)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  toastTitle: {
    fontSize: 13,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.13,
    color: colors.textPrimary,
  },
  toastMeta: {
    fontSize: 11.5,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
  },
});
