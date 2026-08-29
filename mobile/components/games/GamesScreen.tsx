import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import Svg, { Circle, Path } from 'react-native-svg';

import { ScreenHeader } from '@/components/ScreenHeader';
import { GameRow } from '@/components/games/GameRow';
import { AmbientBackdrop } from '@/components/ui/AmbientBackdrop';
import { RiseIn } from '@/components/ui/RiseIn';
import { colors, fonts } from '@/constants/theme';
import { useStudio } from '@/state/StudioContext';

const TAB_CLEAR = 110;

export function GamesScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { state, toggleGameRecording } = useStudio();
  const waiting = state.classifyQueue.length;
  const nextId = state.classifyQueue[0]?.id;
  const recordingCount = state.detectedGames.filter((g) => g.recording).length;

  return (
    <View style={styles.screen}>
      <AmbientBackdrop variant="games" />
      <View style={{ paddingTop: insets.top }}>
        <ScreenHeader variant="large-title" title="Games">
          <View style={styles.segment}>
            <View style={[styles.segItem, styles.segOn]}>
              <Text style={styles.segOnText}>
                Recording · {state.detectedGames.length > 0 ? recordingCount : '—'}
              </Text>
            </View>
            <View style={styles.segItem}>
              <Text style={styles.segOffText}>Not games · {state.notGamesCount ?? '—'}</Text>
            </View>
          </View>
        </ScreenHeader>
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: TAB_CLEAR + insets.bottom }]}
        showsVerticalScrollIndicator={false}>
        {waiting > 0 ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => {
            if (nextId) router.push(`/games/classify/${nextId}`);
          }}
          style={({ pressed }) => [pressed && { transform: [{ scale: 0.985 }] }]}>
          <LinearGradient
            colors={['rgba(245,166,35,0.07)', 'rgba(245,243,255,0.015)']}
            start={{ x: 0.15, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.queueCard}>
            <View style={styles.queueIcon}>
              <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
                <Path
                  d="M12 7.5v5.2M12 16.4h.01"
                  stroke="#F5A623"
                  strokeWidth={1.6}
                  strokeLinecap="round"
                />
                <Circle cx="12" cy="12" r="8.4" stroke="#F5A623" strokeWidth={1.6} />
              </Svg>
            </View>
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={styles.queueTitle}>{waiting} waiting to classify</Text>
              <Text style={styles.queueSub}>Seen while you were away</Text>
            </View>
            <Svg width={15} height={15} viewBox="0 0 24 24" fill="none">
              <Path
                d="m9 5 7 7-7 7"
                stroke="#736BA4"
                strokeWidth={1.7}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </Svg>
          </LinearGradient>
        </Pressable>
        ) : null}

        {state.detectedGames.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No games detected</Text>
            <Text style={styles.emptyBody}>
              Recently seen executables land here, each with a switch for whether Nebula records
              it, once the studio agent reports them.
            </Text>
          </View>
        ) : (
          <View style={{ gap: 8 }}>
            {state.detectedGames.map((game, i) => (
              <RiseIn key={game.id} delay={i * 55}>
                <GameRow game={game} onToggle={() => toggleGameRecording(game.id)} />
              </RiseIn>
            ))}
          </View>
        )}

        <Text style={styles.footnote}>
          Icons come from the executable. The tint behind each is hashed from the name, so a game
          keeps its colour.
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bgScreen },
  segment: {
    height: 36,
    borderRadius: 11,
    backgroundColor: 'rgba(245,243,255,.045)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.07)',
    flexDirection: 'row',
    padding: 3,
    gap: 3,
  },
  segItem: {
    flex: 1,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segOn: {
    backgroundColor: 'rgba(139,124,246,.2)',
    borderWidth: 1,
    borderColor: 'rgba(139,124,246,.34)',
  },
  segOnText: {
    fontSize: 12.5,
    fontFamily: fonts.uiSemi,
    color: colors.textAccentSoft,
  },
  segOffText: {
    fontSize: 12.5,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  body: { paddingHorizontal: 16, gap: 14 },
  queueCard: {
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(245,166,35,.24)',
    paddingVertical: 14,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 13,
  },
  queueIcon: {
    width: 34,
    height: 34,
    borderRadius: 11,
    backgroundColor: 'rgba(245,166,35,.14)',
    borderWidth: 1,
    borderColor: 'rgba(245,166,35,.3)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  queueTitle: {
    fontSize: 13.5,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.135,
    color: colors.textPrimary,
  },
  queueSub: {
    fontSize: 11.5,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  empty: {
    paddingTop: 28,
    alignItems: 'center',
    gap: 10,
  },
  emptyTitle: {
    fontSize: 21,
    fontFamily: fonts.uiSemi,
    color: colors.textPrimary,
  },
  emptyBody: {
    fontSize: 13,
    lineHeight: 20,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
    textAlign: 'center',
    maxWidth: 290,
  },
  footnote: {
    fontSize: 11.5,
    lineHeight: 18,
    fontFamily: fonts.ui,
    color: colors.textLabel,
    paddingHorizontal: 4,
    paddingTop: 8,
  },
});
