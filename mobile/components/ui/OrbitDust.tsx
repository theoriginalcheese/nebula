import { useEffect, useRef } from 'react';
import { Animated, Easing, View } from 'react-native';

type Mote = { orb: number; a: number; size: number; delayMs: number; durationMs: number };

const MOTES: Mote[] = [
  { orb: 52, a: 0.5, size: 3.5, delayMs: 0, durationMs: 4200 },
  { orb: 44, a: 0.34, size: 2.5, delayMs: -1400, durationMs: 4200 },
  { orb: 57, a: 0.26, size: 2, delayMs: -2700, durationMs: 4200 },
  { orb: 37, a: 0.4, size: 2.5, delayMs: -600, durationMs: 6800 },
  { orb: 49, a: 0.22, size: 2, delayMs: -3900, durationMs: 6800 },
];

type Props = { colour: string; motionScale: number; size?: number };

function OrbitMote({
  m,
  colour,
  motionScale,
  box,
}: {
  m: Mote;
  colour: string;
  motionScale: number;
  box: number;
}) {
  const rot = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (motionScale <= 0) {
      rot.stopAnimation();
      return;
    }
    const start = ((m.delayMs % m.durationMs) + m.durationMs) % m.durationMs;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.delay(start),
        Animated.timing(rot, {
          toValue: 1,
          duration: m.durationMs,
          easing: Easing.linear,
          useNativeDriver: true,
        }),
        Animated.timing(rot, { toValue: 0, duration: 0, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [motionScale, m.delayMs, m.durationMs, rot]);

  const spin = rot.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });

  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: 'absolute',
        left: box / 2,
        top: box / 2,
        width: m.orb * 2,
        height: m.orb * 2,
        marginLeft: -m.orb,
        marginTop: -m.orb,
        opacity: motionScale <= 0 ? m.a * 0.3 : m.a,
        transform: [{ rotate: spin }],
      }}>
      <View
        style={{
          position: 'absolute',
          left: m.orb * 2 - m.size / 2,
          top: m.orb - m.size / 2,
          width: m.size,
          height: m.size,
          borderRadius: 999,
          backgroundColor: colour,
        }}
      />
    </Animated.View>
  );
}

export function OrbitDust({ colour, motionScale, size = 118 }: Props) {
  return (
    <View pointerEvents="none" style={{ position: 'absolute', width: size, height: size }}>
      {MOTES.map((m, i) => (
        <OrbitMote key={i} m={m} colour={colour} motionScale={motionScale} box={size} />
      ))}
    </View>
  );
}
