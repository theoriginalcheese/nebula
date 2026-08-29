import { StyleSheet, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { Toggle } from '@/components/ui/Toggle';
import { colors, fonts } from '@/constants/theme';
import type { DetectedGame } from '@/state/studio';

/**
 * Hash the executable name to a hue so a title keeps its colour between
 * launches — the rule the mockup states in its own footnote.
 */
function hashHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i += 1) {
    h = (h * 31 + name.charCodeAt(i)) % 360;
  }
  return h;
}

/**
 * Real per-title art comes from the executable's icon, which needs the agent.
 * Until then the tile is the hashed tint plus a neutral glyph — a placeholder
 * that is honestly a placeholder, not a stand-in for someone else's art.
 */
export function GameRow({
  game,
  onToggle,
  readOnly = false,
}: {
  game: DetectedGame;
  onToggle: () => void;
  readOnly?: boolean;
}) {
  const hue = hashHue(game.exe || game.name);
  const tint = `hsl(${hue}, 62%, 66%)`;

  return (
    <View style={styles.row}>
      <View
        style={[
          styles.tile,
          { backgroundColor: `hsla(${hue}, 62%, 62%, 0.2)`, borderColor: `hsla(${hue}, 62%, 70%, 0.48)` },
        ]}>
        <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
          <Path
            d="M4.6 8.2h14.8a2.6 2.6 0 0 1 2.6 2.6v2.4a2.6 2.6 0 0 1-2.6 2.6H4.6A2.6 2.6 0 0 1 2 13.2v-2.4a2.6 2.6 0 0 1 2.6-2.6Z"
            stroke={tint}
            strokeWidth={1.5}
          />
          <Path
            d="M7.2 10.6v2.8M5.8 12h2.8M15.8 11.2h.01M18 13.2h.01"
            stroke={tint}
            strokeWidth={1.6}
            strokeLinecap="round"
          />
        </Svg>
      </View>

      <View style={styles.copy}>
        <Text style={styles.name} numberOfLines={1}>
          {game.name}
        </Text>
        <Text style={styles.exe} numberOfLines={1}>
          {game.exe}
        </Text>
      </View>

      <Toggle
        value={game.recording}
        onValueChange={onToggle}
        disabled={readOnly}
        accessibilityLabel={`Record ${game.name}`}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    paddingLeft: 10,
    paddingRight: 14,
    borderRadius: 17,
    backgroundColor: colors.rowFill,
    borderWidth: 1,
    borderColor: colors.rowBorder,
  },
  tile: {
    width: 42,
    height: 42,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 3, minWidth: 0 },
  name: {
    fontSize: 14,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.14,
    color: colors.textPrimary,
  },
  exe: {
    fontFamily: fonts.mono,
    fontSize: 10,
    color: colors.textLabel,
  },
});
