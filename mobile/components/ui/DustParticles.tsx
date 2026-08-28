import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

type Particle = { dx: number; dy: number; a: number; size: number; delayMs: number };

const BURST: Particle[] = [
  { dx: -13, dy: -8, a: 0.45, size: 3, delayMs: 0 },
  { dx: 11, dy: -11, a: 0.32, size: 2.5, delayMs: -400 },
  { dx: 15, dy: 6, a: 0.4, size: 2, delayMs: -850 },
  { dx: -9, dy: 12, a: 0.28, size: 2.5, delayMs: -1300 },
  { dx: 4, dy: -16, a: 0.24, size: 2, delayMs: -1700 },
];

const SINK: Particle[] = [
  { dx: -38, dy: -24, a: 0.3, size: 3, delayMs: 0 },
  { dx: 34, dy: -30, a: 0.22, size: 2.5, delayMs: -500 },
  { dx: 42, dy: 18, a: 0.26, size: 2, delayMs: -1100 },
  { dx: -30, dy: 34, a: 0.2, size: 2.5, delayMs: -1600 },
  { dx: 12, dy: 41, a: 0.16, size: 2, delayMs: -2200 },
];

type Props = {
  mode: 'burst' | 'sink';
  colour: string;
  motionScale: number;
  size?: number;
};

function DustDot({
  p,
  colour,
  mode,
  motionScale,
  box,
}: {
  p: Particle;
  colour: string;
  mode: 'burst' | 'sink';
  motionScale: number;
  box: number;
}) {
  const t = useRef(new Animated.Value(0)).current;
  const duration = mode === 'burst' ? 2400 : 2800;
  const travel = mode === 'burst' ? 1.35 : 0.4;
  const sinkY = mode === 'sink' ? 4 : 0;

  useEffect(() => {
    if (motionScale <= 0) {
      t.stopAnimation();
      t.setValue(0);
      return;
    }
    const startDelay = ((p.delayMs % duration) + duration) % duration;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.delay(startDelay),
        Animated.timing(t, {
          toValue: 1,
          duration,
          easing: Easing.bezier(0.32, 0.72, 0, 1),
          useNativeDriver: true,
        }),
        Animated.timing(t, { toValue: 0, duration: 0, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [motionScale, mode, duration, p.delayMs, t]);

  const tx = t.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [0, p.dx * travel, 0],
  });
  const ty = t.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [0, p.dy * travel + sinkY, 0],
  });
  const scale = t.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: mode === 'burst' ? [1, 1.15, 1] : [1, 1, 1],
  });
  const opacity = t.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [p.a, p.a * (mode === 'burst' ? 0.55 : 0.7), p.a],
  });

  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: 'absolute',
        left: box / 2,
        top: box / 2,
        width: p.size,
        height: p.size,
        marginLeft: -p.size / 2,
        marginTop: -p.size / 2,
        borderRadius: 999,
        backgroundColor: colour,
        opacity: motionScale <= 0 ? p.a * 0.35 : opacity,
        transform: [{ translateX: tx }, { translateY: ty }, { scale }],
      }}
    />
  );
}

export function DustParticles({ mode, colour, motionScale, size = 28 }: Props) {
  const particles = mode === 'burst' ? BURST : SINK;
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { width: size, height: size }]}>
      {particles.map((p, i) => (
        <DustDot key={i} p={p} colour={colour} mode={mode} motionScale={motionScale} box={size} />
      ))}
    </View>
  );
}
