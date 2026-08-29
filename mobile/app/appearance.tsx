import { useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path } from 'react-native-svg';

import { AmbientBackdrop } from '@/components/ui/AmbientBackdrop';
import { DustParticles } from '@/components/ui/DustParticles';
import { Eyebrow } from '@/components/ui/Eyebrow';
import { FadeRule } from '@/components/ui/FadeRule';
import { LargeTitle } from '@/components/ui/LargeTitle';
import { SoftCard } from '@/components/ui/SoftCard';
import { Toggle } from '@/components/ui/Toggle';
import { accentPresets, colors, fonts } from '@/constants/theme';
import { useStudio } from '@/state/StudioContext';

/**
 * Appearance (#f-appearance).
 *
 * DESIGN GAP: none of the eight mockup frames link here, and the frame shows
 * the tab bar with no tab highlighted — which a four-tab bar cannot express.
 * The route therefore stays reachable-but-unlinked rather than getting an
 * invented gear icon. Product decision needed; see the build report.
 */
export default function AppearanceScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const {
    state,
    accent,
    accentHex,
    accentSoft,
    setAccent,
    motionScale,
    setMotionScale,
    reduceMotionFromSystem,
    haptics,
    setHaptics,
  } = useStudio();

  // The mockup prints a multiplier against its own 0–100 slider (60% = 1.00×).
  // Here motionScale is already 0–1 with 1 = full motion, so a plain percentage
  // is the unambiguous readout.
  const motionLabel = reduceMotionFromSystem
    ? 'off · system'
    : motionScale <= 0.06
      ? 'off'
      : `${Math.round(motionScale * 100)}%`;

  return (
    <View style={styles.screen}>
      <AmbientBackdrop variant="games" />

      <View style={[styles.header, { paddingTop: insets.top + 2 }]}>
        <Pressable onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Svg width={17} height={17} viewBox="0 0 24 24" fill="none">
            <Path
              d="m15 5-7 7 7 7"
              stroke={colors.textStudio}
              strokeWidth={1.8}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </Svg>
        </Pressable>
        <LargeTitle>Appearance</LargeTitle>
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: 40 + insets.bottom }]}
        showsVerticalScrollIndicator={false}>
        <SoftCard innerStyle={styles.accentInner}>
          <DustParticles
            mode="scatter"
            colour={accentHex}
            motionScale={motionScale}
            size={120}
          />
          <View style={styles.rowBetween}>
            <Eyebrow>Accent</Eyebrow>
            <Text style={[styles.mono, { color: accentSoft }]}>{accentHex}</Text>
          </View>

          <View style={styles.swatches}>
            {accentPresets.map((preset) => {
              const on = preset.id === accent;
              return (
                <Pressable
                  key={preset.id}
                  accessibilityRole="button"
                  accessibilityLabel={`${preset.id} accent`}
                  accessibilityState={{ selected: on }}
                  onPress={() => setAccent(preset.id)}
                  style={({ pressed }) => [
                    styles.swatch,
                    { backgroundColor: preset.hex },
                    on && { borderColor: colors.textPrimary, borderWidth: 2 },
                    pressed && { transform: [{ scale: 0.94 }] },
                  ]}
                />
              );
            })}
          </View>

          <Text style={styles.note}>
            The ground is never themeable, and ember stays out of the set so a real disconnection
            still reads as one.
          </Text>
        </SoftCard>

        <SoftCard innerStyle={styles.slidersInner}>
          <View style={{ gap: 9 }}>
            <View style={styles.rowBetween}>
              <Text style={styles.settingLabel}>Motion</Text>
              <Text style={[styles.monoSmall, { color: accentSoft }]}>{motionLabel}</Text>
            </View>
            <Slider
              value={motionScale}
              onChange={setMotionScale}
              fill={accentHex}
              disabled={reduceMotionFromSystem}
            />
            <Text style={styles.note}>
              {reduceMotionFromSystem
                ? 'Held at zero by Reduce Motion in iOS accessibility settings. Turn that off to adjust motion here.'
                : 'Drives every ambient animation in the app. At zero the arc, orb, dust and list entrances all stop — this is the reduce-motion control.'}
            </Text>
          </View>

          <FadeRule />

          {/*
            Density and Corner radius are in the mockup but need a runtime token
            scale (every spacing and radius value) before they can do anything.
            Shown as pending rather than as sliders that move and change nothing.
          */}
          <View style={{ gap: 12 }}>
            {(['Density', 'Corner radius'] as const).map((label) => (
              <View key={label} style={styles.rowBetween}>
                <Text style={[styles.settingLabel, styles.settingPending]}>{label}</Text>
                <Text style={styles.pendingTag}>not wired yet</Text>
              </View>
            ))}
          </View>

          <FadeRule />

          <View style={styles.rowBetween}>
            <Text style={styles.settingLabel}>Haptics on transport</Text>
            <Toggle
              value={haptics}
              onValueChange={() => setHaptics(!haptics)}
              accessibilityLabel="Haptics on transport"
            />
          </View>
        </SoftCard>

        <SoftCard innerStyle={{ gap: 12 }}>
          <Eyebrow>Notification preview</Eyebrow>
          <View style={styles.preview}>
            <View
              style={[
                styles.previewIcon,
                { backgroundColor: `${accentHex}22`, borderColor: `${accentHex}55` },
              ]}>
              <Svg width={13} height={13} viewBox="0 0 24 24" fill="none">
                <Circle cx="12" cy="12" r="5.4" stroke={accentHex} strokeWidth={1.7} />
              </Svg>
            </View>
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={styles.previewTitle}>Recording started</Text>
              {/* Real session values when the agent has reported them — never a stand-in title. */}
              <Text style={styles.previewMeta}>
                {[state.recording.gameTitle, state.recording.encoder].filter(Boolean).join(' · ') ||
                  'Your game and encoder appear here once a session starts'}
              </Text>
            </View>
          </View>
        </SoftCard>
      </ScrollView>
    </View>
  );
}

/** 4px track, accent fill, drag anywhere on the track to set (as in the mockup). */
function Slider({
  value,
  onChange,
  fill,
  disabled = false,
}: {
  value: number;
  onChange: (n: number) => void;
  fill: string;
  disabled?: boolean;
}) {
  const width = useRef(0);
  const set = (x: number) => {
    if (disabled || width.current <= 0) return;
    onChange(Math.max(0, Math.min(1, x / width.current)));
  };

  return (
    <View
      accessibilityRole="adjustable"
      accessibilityState={{ disabled }}
      accessibilityValue={{ min: 0, max: 100, now: Math.round(value * 100) }}
      style={[styles.track, disabled && { opacity: 0.45 }]}
      onLayout={(e) => {
        width.current = e.nativeEvent.layout.width;
      }}
      onStartShouldSetResponder={() => !disabled}
      onMoveShouldSetResponder={() => !disabled}
      onResponderGrant={(e) => set(e.nativeEvent.locationX)}
      onResponderMove={(e) => set(e.nativeEvent.locationX)}>
      <View style={[styles.trackFill, { width: `${value * 100}%`, backgroundColor: fill }]} />
      <View
        style={[styles.knob, { left: `${value * 100}%`, borderColor: fill }]}
        pointerEvents="none"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bgScreen },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 20,
    paddingBottom: 14,
  },
  back: {
    width: 30,
    height: 30,
    borderRadius: 999,
    backgroundColor: 'rgba(245,243,255,.05)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { paddingHorizontal: 16, gap: 12 },
  accentInner: { paddingTop: 15, paddingBottom: 15, gap: 13, overflow: 'hidden' },
  slidersInner: { paddingTop: 15, paddingBottom: 15, gap: 14 },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  mono: { fontFamily: fonts.mono, fontSize: 10.5 },
  monoSmall: { fontFamily: fonts.mono, fontSize: 11 },
  swatches: { flexDirection: 'row', gap: 10 },
  swatch: {
    width: 34,
    height: 34,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.14)',
  },
  note: {
    fontSize: 11.5,
    lineHeight: 18,
    fontFamily: fonts.ui,
    color: colors.textLabel,
  },
  settingLabel: {
    fontSize: 13,
    fontFamily: fonts.ui,
    color: colors.textPrimary,
  },
  settingPending: { color: colors.textMuted },
  pendingTag: {
    fontFamily: fonts.mono,
    fontSize: 10,
    color: colors.textLabel,
  },
  track: {
    height: 22,
    justifyContent: 'center',
  },
  trackFill: {
    position: 'absolute',
    left: 0,
    height: 4,
    borderRadius: 999,
  },
  knob: {
    position: 'absolute',
    width: 14,
    height: 14,
    marginLeft: -7,
    borderRadius: 999,
    backgroundColor: colors.textPrimary,
    borderWidth: 2,
  },
  preview: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 12,
    borderRadius: 16,
    backgroundColor: colors.rowFill,
    borderWidth: 1,
    borderColor: colors.rowBorder,
  },
  previewIcon: {
    width: 30,
    height: 30,
    borderRadius: 999,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  previewTitle: {
    fontSize: 13,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.13,
    color: colors.textPrimary,
  },
  previewMeta: {
    fontSize: 11.5,
    lineHeight: 17,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
  },
});
