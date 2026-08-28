import Svg, { Defs, Ellipse, LinearGradient, Path, Stop } from 'react-native-svg';

import { colors } from '@/constants/theme';

type Props = { size?: number; muted?: boolean };

export function NebulaMark({ size = 22, muted = false }: Props) {
  if (muted) {
    return (
      <Svg width={size} height={size} viewBox="-8 -8 80 80">
        <Ellipse
          cx="32"
          cy="32"
          rx="29.44"
          ry="17.66"
          fill="none"
          stroke="#A29BC0"
          strokeWidth="4.4"
          transform="rotate(-22 32 32)"
        />
        <Defs>
          <LinearGradient id="nmDeadMark" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#A29BC0" />
            <Stop offset="1" stopColor="#6E6888" />
          </LinearGradient>
        </Defs>
        <Path
          d="M53.76 32 37.23 37.23 32 53.76 26.77 37.23 10.24 32 26.77 26.77 32 10.24 37.23 26.77Z"
          fill="url(#nmDeadMark)"
        />
      </Svg>
    );
  }

  return (
    <Svg width={size} height={size} viewBox="-8 -8 80 80">
      <Defs>
        <LinearGradient id="nmGold" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#FFE8BC" />
          <Stop offset="1" stopColor="#F5A623" />
        </LinearGradient>
        <LinearGradient id="nmSpark" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#C9BFFF" />
          <Stop offset="1" stopColor={colors.accentDefault} />
        </LinearGradient>
      </Defs>
      <Ellipse
        cx="32"
        cy="32"
        rx="29.44"
        ry="17.66"
        fill="none"
        stroke="url(#nmGold)"
        strokeWidth="4.4"
        transform="rotate(-22 32 32)"
      />
      <Path
        d="M53.76 32 37.23 37.23 32 53.76 26.77 37.23 10.24 32 26.77 26.77 32 10.24 37.23 26.77Z"
        fill="url(#nmSpark)"
      />
    </Svg>
  );
}
