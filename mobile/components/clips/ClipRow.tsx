import { StyleSheet, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { colors, fonts } from '@/constants/theme';
import type { Clip } from '@/state/studio';

/** Trailing state glyph — live dot, NAS tick, offload arrow, or nothing. */
function StateMark({ state }: { state: Clip['state'] }) {
  switch (state) {
    case 'recording':
      return <View style={styles.liveDot} />;
    case 'on-nas':
      return (
        <Svg width={15} height={15} viewBox="0 0 24 24" fill="none">
          <Path
            d="M20 6 9 17l-5-5"
            stroke={colors.textStudio}
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </Svg>
      );
    case 'offloading':
      return (
        <Svg width={15} height={15} viewBox="0 0 24 24" fill="none">
          <Path
            d="M12 3.5v11M7.8 10.4 12 14.6l4.2-4.2M4.6 18.5h14.8"
            stroke={colors.textStudio}
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </Svg>
      );
    default:
      return null;
  }
}

const STATE_WORD: Record<Clip['state'], string> = {
  recording: 'recording',
  local: 'on this PC',
  offloading: 'offloading',
  'on-nas': 'on NAS',
};

export function ClipRow({ clip }: { clip: Clip }) {
  const live = clip.state === 'recording';
  const meta = [clip.sizeLabel, STATE_WORD[clip.state]].filter(Boolean).join(' · ');

  return (
    <View style={[styles.row, live && styles.rowLive]}>
      <View style={[styles.duration, live && styles.durationLive]}>
        <Text style={[styles.durationText, live && styles.durationTextLive]}>
          {clip.durationLabel ?? '—'}
        </Text>
      </View>
      <View style={styles.copy}>
        <Text style={styles.title} numberOfLines={1}>
          {clip.title}
        </Text>
        <Text style={styles.meta} numberOfLines={1}>
          {meta || '—'}
        </Text>
      </View>
      <View style={styles.mark}>
        <StateMark state={clip.state} />
      </View>
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
  rowLive: {
    backgroundColor: 'rgba(245,166,35,.06)',
    borderColor: 'rgba(245,166,35,.22)',
  },
  duration: {
    minWidth: 62,
    height: 42,
    borderRadius: 12,
    backgroundColor: 'rgba(139,124,246,.14)',
    borderWidth: 1,
    borderColor: 'rgba(139,124,246,.26)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  durationLive: {
    backgroundColor: 'rgba(245,166,35,.14)',
    borderColor: 'rgba(245,166,35,.3)',
  },
  durationText: {
    fontFamily: fonts.mono,
    fontSize: 12,
    color: colors.textAccentSoft,
    fontVariant: ['tabular-nums'],
  },
  durationTextLive: { color: colors.goldText },
  copy: { flex: 1, gap: 3, minWidth: 0 },
  title: {
    fontSize: 14,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.14,
    color: colors.textPrimary,
  },
  meta: {
    fontFamily: fonts.mono,
    fontSize: 10,
    color: colors.textLabel,
  },
  mark: { width: 15, alignItems: 'center' },
  liveDot: {
    width: 7,
    height: 7,
    borderRadius: 999,
    backgroundColor: colors.accentAmber,
  },
});
