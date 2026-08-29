import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

import { OrbitDust } from '@/components/ui/OrbitDust';
import { colors } from '@/constants/theme';
import type { MoonState } from '@/state/studio';

const SIZE = 118;

/** Motion carries state: slow while ready, quick during handshake, gold when live. */
const PULSE_MS: Record<MoonState, number> = {
  ready: 2600,
  busy: 900,
  live: 1800,
};

const TINT: Record<MoonState, { core: string; glow: string; ring: string; dust: string }> = {
  ready: {
    core: 'rgba(139,124,246,.55)',
    glow: 'rgba(139,124,246,.34)',
    ring: 'rgba(139,124,246,.34)',
    dust: colors.textAccentSoft,
  },
  busy: {
    core: 'rgba(139,124,246,.7)',
    glow: 'rgba(139,124,246,.44)',
    ring: 'rgba(139,124,246,.5)',
    dust: colors.textAccentSoft,
  },
  live: {
    core: 'rgba(245,166,35,.55)',
    glow: 'rgba(245,166,35,.36)',
    ring: 'rgba(245,166,35,.38)',
    dust: colors.goldText,
  },
};

export function MoonlightOrb({
  state,
  motionScale,
}: {
  state: MoonState;
  motionScale: number;
}) {
  const pulse = useRef(new Animated.Value(0)).current;
  const tint = TINT[state];

  useEffect(() => {
    if (motionScale <= 0) {
      pulse.stopAnimation();
      pulse.setValue(0);
      return;
    }
    const half = PULSE_MS[state] / 2;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: half,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: half,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [state, motionScale, pulse]);

  // nm-orb / nm-orb2: the halo breathes, the counter-ring breathes against it.
  const glowScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.16] });
  const glowOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.5, 0.85] });
  const ringScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1.1, 0.94] });
  const ringOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.28, 0.6] });

  return (
    <View style={styles.wrap}>
      <Animated.View
        style={[
          styles.glow,
          {
            backgroundColor: tint.glow,
            opacity: glowOpacity,
            transform: [{ scale: glowScale }],
          },
        ]}
      />
      <Animated.View
        style={[
          styles.ring1,
          { borderColor: tint.ring, opacity: ringOpacity, transform: [{ scale: ringScale }] },
        ]}
      />
      <View style={[styles.ring2, { borderColor: tint.ring }]} />
      <OrbitDust colour={tint.dust} motionScale={motionScale} size={SIZE} />
      <View style={[styles.core, { backgroundColor: tint.core }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: SIZE,
    height: SIZE,
    alignItems: 'center',
    justifyContent: 'center',
  },
  glow: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 999,
  },
  ring1: {
    position: 'absolute',
    top: 14,
    left: 14,
    right: 14,
    bottom: 14,
    borderRadius: 999,
    borderWidth: 1,
  },
  ring2: {
    position: 'absolute',
    top: 30,
    left: 30,
    right: 30,
    bottom: 30,
    borderRadius: 999,
    borderWidth: 1,
    opacity: 0.6,
  },
  core: {
    width: 56,
    height: 56,
    borderRadius: 999,
  },
});
