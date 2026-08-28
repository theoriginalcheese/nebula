import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

import { colors } from '@/constants/theme';
import { useStudio } from '@/state/StudioContext';

type Props = { variant?: 'now' | 'offline' | 'remote' | 'clips' | 'games' };

function SoftBlob({
  style,
  color,
  duration,
  motionScale,
}: {
  style: object;
  color: string;
  duration: number;
  motionScale: number;
}) {
  const drift = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (motionScale <= 0) {
      drift.stopAnimation();
      drift.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(drift, {
          toValue: 1,
          duration,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(drift, {
          toValue: 0,
          duration,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [drift, duration, motionScale]);

  const tx = drift.interpolate({ inputRange: [0, 1], outputRange: [0, 18] });
  const ty = drift.interpolate({ inputRange: [0, 1], outputRange: [0, -14] });

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        {
          position: 'absolute',
          borderRadius: 9999,
          backgroundColor: color,
          transform: [{ translateX: tx }, { translateY: ty }],
        },
        style,
      ]}
    />
  );
}

export function AmbientBackdrop({ variant = 'now' }: Props) {
  const { motionScale } = useStudio();

  const config =
    variant === 'offline'
      ? {
          a: { top: '-12%', left: '-20%', width: '90%', height: '48%', color: 'rgba(154,147,196,0.2)' },
          b: { top: '28%', right: '-22%', width: '78%', height: '40%', color: 'rgba(255,92,122,0.1)' },
          durA: 62000,
          durB: 78000,
        }
      : variant === 'remote'
        ? {
            a: { top: '0%', left: '-14%', width: '92%', height: '50%', color: 'rgba(139,124,246,0.32)' },
            b: { bottom: '4%', right: '-20%', width: '80%', height: '40%', color: 'rgba(94,168,205,0.16)' },
            durA: 66000,
            durB: 84000,
          }
        : variant === 'games'
          ? {
              a: { top: '-14%', right: '-18%', width: '88%', height: '46%', color: 'rgba(139,124,246,0.24)' },
              b: null as null,
              durA: 70000,
              durB: 80000,
            }
          : variant === 'clips'
            ? {
                a: { top: '-14%', left: '-20%', width: '90%', height: '46%', color: 'rgba(139,124,246,0.26)' },
                b: null as null,
                durA: 70000,
                durB: 80000,
              }
            : {
                a: { top: '-12%', left: '-18%', width: '92%', height: '50%', color: colors.violetGlow },
                b: { top: '22%', right: '-22%', width: '80%', height: '42%', color: colors.amberGlow },
                durA: 62000,
                durB: 78000,
              };

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <SoftBlob
        color={config.a.color}
        duration={config.durA}
        motionScale={motionScale}
        style={{
          top: config.a.top,
          left: (config.a as { left?: string }).left,
          right: (config.a as { right?: string }).right,
          width: config.a.width,
          height: config.a.height,
          opacity: 0.9,
        }}
      />
      {config.b ? (
        <SoftBlob
          color={config.b.color}
          duration={config.durB}
          motionScale={motionScale}
          style={{
            top: (config.b as { top?: string }).top,
            bottom: (config.b as { bottom?: string }).bottom,
            right: (config.b as { right?: string }).right,
            width: config.b.width,
            height: config.b.height,
            opacity: 0.85,
          }}
        />
      ) : null}
    </View>
  );
}
