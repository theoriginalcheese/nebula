import Svg, { Defs, Ellipse, LinearGradient, Path, Stop } from 'react-native-svg';
import { View } from 'react-native';

import { DustParticles } from '@/components/ui/DustParticles';

type Props = { size?: number; motionScale?: number };

/** Offline starburst with diagonal slash — matches f-offline dc.html */
export function DeadMark({ size = 96, motionScale = 1 }: Props) {
  return (
    <View style={{ width: size, height: size }}>
      <DustParticles mode="sink" colour="#8C86A8" motionScale={motionScale} size={size} />
      <Svg width={size} height={size} viewBox="-8 -8 80 80" style={{ zIndex: 1 }}>
        <Defs>
          <LinearGradient id="nmDead" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#A29BC0" />
            <Stop offset="1" stopColor="#6E6888" />
          </LinearGradient>
        </Defs>
        <Ellipse
          cx="32"
          cy="32"
          rx="25.98"
          ry="10.5"
          fill="none"
          stroke="#8C86A8"
          strokeWidth="1.5"
          opacity={0.45}
          transform="rotate(48 32 32)"
        />
        <Ellipse
          cx="32"
          cy="32"
          rx="29.44"
          ry="17.66"
          fill="none"
          stroke="#A29BC0"
          strokeWidth="3.4"
          transform="rotate(-22 32 32)"
        />
        <Path
          d="M53.76 32 37.23 37.23 32 53.76 26.77 37.23 10.24 32 26.77 26.77 32 10.24 37.23 26.77Z"
          fill="url(#nmDead)"
        />
        <Path d="M8.96 55.04 55.04 8.96" stroke="#181428" strokeWidth="9.28" />
        <Path d="M8.96 55.04 55.04 8.96" stroke="#B7B1D0" strokeWidth="4.6" strokeLinecap="round" />
      </Svg>
    </View>
  );
}
