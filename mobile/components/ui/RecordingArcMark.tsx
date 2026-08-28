import { useEffect, useRef } from 'react';
import { Animated, Easing, View } from 'react-native';
import Svg, { Defs, Ellipse, LinearGradient, Path, Stop } from 'react-native-svg';

import { colors } from '@/constants/theme';

const AnimatedSvg = Animated.createAnimatedComponent(Svg);

type Props = { spinning: boolean; size?: number };

export function RecordingArcMark({ spinning, size = 52 }: Props) {
  const rot = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!spinning) {
      rot.stopAnimation();
      rot.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.timing(rot, {
        toValue: 1,
        duration: 3800,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [spinning, rot]);

  const spin = rot.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });

  return (
    <View style={{ width: size, height: size, marginTop: -2 }}>
      <Svg width={size} height={size} viewBox="-8 -8 80 80" style={StyleSheetAbs}>
        <Defs>
          <LinearGradient id="arcGold" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#FFE8BC" />
            <Stop offset="1" stopColor="#F5A623" />
          </LinearGradient>
          <LinearGradient id="arcSpark" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#C9BFFF" />
            <Stop offset="1" stopColor={colors.accentDefault} />
          </LinearGradient>
        </Defs>
        <Ellipse
          cx="32"
          cy="32"
          rx="25.98"
          ry="10.5"
          fill="none"
          stroke={colors.accentDefault}
          strokeWidth="1.7"
          opacity={0.45}
          transform="rotate(48 32 32)"
        />
        <Ellipse
          cx="32"
          cy="32"
          rx="29.44"
          ry="17.66"
          fill="none"
          stroke="url(#arcGold)"
          strokeWidth="3.6"
          opacity={0.5}
          transform="rotate(-22 32 32)"
        />
        <Path
          d="M53.76 32 37.23 37.23 32 53.76 26.77 37.23 10.24 32 26.77 26.77 32 10.24 37.23 26.77Z"
          fill="url(#arcSpark)"
        />
      </Svg>
      {spinning ? (
        <Animated.View
          style={{
            ...StyleSheetAbs,
            width: size,
            height: size,
            transform: [{ rotate: spin }],
          }}>
          <Svg width={size} height={size} viewBox="-8 -8 80 80">
            <Ellipse
              cx="32"
              cy="32"
              rx="29.44"
              ry="17.66"
              fill="none"
              stroke={colors.goldText}
              strokeWidth="3.6"
              strokeLinecap="round"
              strokeDasharray="24 130"
              transform="rotate(-22 32 32)"
            />
          </Svg>
        </Animated.View>
      ) : null}
    </View>
  );
}

const StyleSheetAbs = {
  position: 'absolute' as const,
  left: 0,
  top: 0,
};
