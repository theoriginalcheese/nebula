import { useEffect, useRef } from 'react';
import { Animated, Easing, ViewProps } from 'react-native';

import { useStudio } from '@/state/StudioContext';

type Props = ViewProps & {
  children: React.ReactNode;
  /** Stagger offset in ms — list rows arrive one after another, once. */
  delay?: number;
  /** Travel distance; 10px for nm-rise, 26px for nm-in. */
  distance?: number;
};

/**
 * `nm-in` / `nm-rise` entrance — plays once on arrival, never loops.
 * Skipped entirely when the Motion setting is at zero (reduce-motion hook).
 */
export function RiseIn({ children, delay = 0, distance = 10, style, ...rest }: Props) {
  const { motionScale } = useStudio();
  const enabled = motionScale > 0;
  const t = useRef(new Animated.Value(enabled ? 0 : 1)).current;

  useEffect(() => {
    if (!enabled) {
      t.setValue(1);
      return;
    }
    const anim = Animated.timing(t, {
      toValue: 1,
      duration: 500,
      delay,
      easing: Easing.bezier(0.32, 0.72, 0, 1),
      useNativeDriver: true,
    });
    anim.start();
    return () => anim.stop();
  }, [delay, enabled, t]);

  return (
    <Animated.View
      style={[
        {
          opacity: t,
          transform: [
            { translateY: t.interpolate({ inputRange: [0, 1], outputRange: [distance, 0] }) },
          ],
        },
        style,
      ]}
      {...rest}>
      {children}
    </Animated.View>
  );
}
