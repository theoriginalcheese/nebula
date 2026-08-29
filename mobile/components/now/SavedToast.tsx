import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { colors, fonts } from '@/constants/theme';

const IN_MS = 290;
const HOLD_MS = 1730;
const OUT_MS = 380;

/**
 * "Recording saved" toast — the `nm-toast` keyframe from the mockup: slides up
 * from the bottom, holds, then lifts out and auto-dismisses. Honours
 * reduce-motion by appearing and leaving without the slide.
 */
export function SavedToast({
  fileSizeLabel,
  bottom,
  motionScale,
  onDone,
}: {
  fileSizeLabel: string | null;
  bottom: number;
  motionScale: number;
  onDone: () => void;
}) {
  const t = useRef(new Animated.Value(0)).current;
  const reduced = motionScale <= 0;

  useEffect(() => {
    const seq = Animated.sequence([
      Animated.timing(t, {
        toValue: 1,
        duration: reduced ? 0 : IN_MS,
        easing: Easing.bezier(0.32, 0.72, 0, 1),
        useNativeDriver: true,
      }),
      Animated.delay(HOLD_MS),
      Animated.timing(t, {
        toValue: 2,
        duration: reduced ? 0 : OUT_MS,
        easing: Easing.bezier(0.32, 0.72, 0, 1),
        useNativeDriver: true,
      }),
    ]);
    seq.start(({ finished }) => {
      if (finished) onDone();
    });
    return () => seq.stop();
  }, [onDone, reduced, t]);

  const opacity = t.interpolate({ inputRange: [0, 1, 2], outputRange: [0, 1, 0] });
  const translateY = t.interpolate({ inputRange: [0, 1, 2], outputRange: [14, 0, -6] });
  const scale = t.interpolate({ inputRange: [0, 1, 2], outputRange: [0.96, 1, 0.99] });

  return (
    <Animated.View
      pointerEvents="none"
      style={[styles.toast, { bottom, opacity, transform: [{ translateY }, { scale }] }]}>
      <View style={styles.icon}>
        <Svg width={14} height={14} viewBox="0 0 24 24" fill="none">
          <Path
            d="M20 6 9 17l-5-5"
            stroke={colors.textAccentSoft}
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </Svg>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.title}>Recording saved</Text>
        <Text style={styles.meta}>{fileSizeLabel ?? '—'}</Text>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute',
    left: 20,
    right: 20,
    zIndex: 5,
    borderRadius: 18,
    backgroundColor: colors.toastBg,
    borderWidth: 1,
    borderColor: colors.toastBorder,
    paddingVertical: 13,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  icon: {
    width: 30,
    height: 30,
    borderRadius: 999,
    backgroundColor: colors.toastIconBg,
    borderWidth: 1,
    borderColor: 'rgba(139,124,246,.4)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 13,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.13,
    color: colors.textPrimary,
  },
  meta: {
    fontSize: 11.5,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
  },
});
