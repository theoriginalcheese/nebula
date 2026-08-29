import { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, StyleSheet } from 'react-native';

import { colors } from '@/constants/theme';

type Props = {
  value: boolean;
  onValueChange: () => void;
  accessibilityLabel?: string;
};

/**
 * 48×29 pill toggle from the mockup's game rows and Appearance haptics row.
 * Track and knob cross-fade over 420ms on the shared ease; the knob slides
 * rather than the whole control flashing colour.
 */
export function Toggle({ value, onValueChange, accessibilityLabel }: Props) {
  const t = useRef(new Animated.Value(value ? 1 : 0)).current;

  useEffect(() => {
    Animated.timing(t, {
      toValue: value ? 1 : 0,
      duration: 420,
      // Shared --ease cubic-bezier(.32,.72,0,1)
      easing: Easing.bezier(0.32, 0.72, 0, 1),
      useNativeDriver: false,
    }).start();
  }, [value, t]);

  const trackColour = t.interpolate({
    inputRange: [0, 1],
    outputRange: [colors.toggleOffTrack, colors.toggleOnTrack],
  });
  const borderColour = t.interpolate({
    inputRange: [0, 1],
    outputRange: [colors.toggleOffBorder, colors.toggleOnBorder],
  });
  const knobColour = t.interpolate({
    inputRange: [0, 1],
    outputRange: [colors.textLabel, colors.textPrimary],
  });
  // 48 wide − 2×2.5 padding − 2×1 border − 23 knob = 18px of travel
  const knobX = t.interpolate({ inputRange: [0, 1], outputRange: [0, 18] });

  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityState={{ checked: value }}
      accessibilityLabel={accessibilityLabel}
      onPress={onValueChange}
      hitSlop={6}>
      <Animated.View
        style={[styles.track, { backgroundColor: trackColour, borderColor: borderColour }]}>
        <Animated.View
          style={[
            styles.knob,
            { backgroundColor: knobColour, transform: [{ translateX: knobX }] },
          ]}
        />
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  track: {
    width: 48,
    height: 29,
    borderRadius: 999,
    borderWidth: 1,
    padding: 2.5,
    justifyContent: 'center',
  },
  knob: {
    width: 23,
    height: 23,
    borderRadius: 999,
  },
});
