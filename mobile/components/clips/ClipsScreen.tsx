import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path } from 'react-native-svg';

import { ClipRow } from '@/components/clips/ClipRow';
import { ScreenHeader } from '@/components/ScreenHeader';
import { AmbientBackdrop } from '@/components/ui/AmbientBackdrop';
import { Eyebrow } from '@/components/ui/Eyebrow';
import { RiseIn } from '@/components/ui/RiseIn';
import { SoftCard } from '@/components/ui/SoftCard';
import { colors, fonts } from '@/constants/theme';
import { groupClipsByDay } from '@/state/studio';
import { useStudio } from '@/state/StudioContext';

const TAB_CLEAR = 110;
const ALL = 'All';

export function ClipsScreen() {
  const insets = useSafeAreaInsets();
  const { state } = useStudio();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<string>(ALL);

  const clips = state.clips;

  // Chips are derived from clips that actually exist — never a hardcoded roster.
  const chips = useMemo(() => {
    const games = new Set<string>();
    for (const clip of clips) if (clip.game) games.add(clip.game);
    return [ALL, ...Array.from(games)];
  }, [clips]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return clips.filter((clip) => {
      if (filter !== ALL && clip.game !== filter) return false;
      if (!q) return true;
      return (
        clip.title.toLowerCase().includes(q) || (clip.game ?? '').toLowerCase().includes(q)
      );
    });
  }, [clips, filter, query]);

  const days = useMemo(() => groupClipsByDay(visible), [visible]);
  const today = days.find((d) => d.label === 'Today');

  return (
    <View style={styles.screen}>
      <AmbientBackdrop variant="clips" />
      <View style={{ paddingTop: insets.top }}>
        <ScreenHeader variant="large-title" title="Clips">
          <View style={styles.search}>
            <Svg width={15} height={15} viewBox="0 0 24 24" fill="none">
              <Circle cx="11" cy="11" r="6.4" stroke={colors.textLabel} strokeWidth={1.6} />
              <Path
                d="m16 16 4 4"
                stroke={colors.textLabel}
                strokeWidth={1.6}
                strokeLinecap="round"
              />
            </Svg>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search clips"
              placeholderTextColor={colors.textLabel}
              style={styles.searchInput}
              autoCorrect={false}
              returnKeyType="search"
              clearButtonMode="while-editing"
            />
          </View>
        </ScreenHeader>
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: TAB_CLEAR + insets.bottom }]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        {/*
          Day ribbon. The mockup draws a bar per clip with a gold "live" bar at
          the end; with no clip metadata synced there is nothing to plot, so it
          says so rather than drawing invented bars.
        */}
        <SoftCard innerStyle={styles.ribbonInner}>
          <View style={styles.ribbonHead}>
            <Eyebrow>Today</Eyebrow>
            <Text style={styles.ribbonMeta}>{today?.meta ?? '—'}</Text>
          </View>
          {today && today.clips.length > 0 ? (
            <View style={styles.ribbonBars}>
              {today.clips.map((clip) => (
                <View
                  key={clip.id}
                  style={[styles.bar, clip.state === 'recording' && styles.barLive]}
                />
              ))}
            </View>
          ) : (
            <View style={styles.ribbonEmpty}>
              <Text style={styles.ribbonEmptyText}>No session activity yet</Text>
            </View>
          )}
        </SoftCard>

        {chips.length > 1 ? (
          <View style={styles.chips}>
            {chips.map((chip) => {
              const on = chip === filter;
              return (
                <Pressable
                  key={chip}
                  onPress={() => setFilter(chip)}
                  style={({ pressed }) => [
                    styles.chip,
                    on && styles.chipOn,
                    pressed && { transform: [{ scale: 0.97 }] },
                  ]}>
                  <Text style={on ? styles.chipOnText : styles.chipText}>{chip}</Text>
                </Pressable>
              );
            })}
          </View>
        ) : null}

        {clips.length === 0 ? (
          <View style={styles.emptyList}>
            <Text style={styles.emptyTitle}>No clips yet</Text>
            <Text style={styles.emptyBody}>
              Day-grouped recordings appear here once the studio link syncs clip metadata.
            </Text>
          </View>
        ) : days.length === 0 ? (
          <View style={styles.emptyList}>
            <Text style={styles.emptyTitle}>Nothing matches</Text>
            <Text style={styles.emptyBody}>
              No clip matches that search or filter. Clear it to see everything again.
            </Text>
          </View>
        ) : (
          days.map((day) => (
            <View key={day.key} style={{ gap: 10 }}>
              <View style={styles.dayHead}>
                <Eyebrow>{day.label}</Eyebrow>
                {day.meta ? <Text style={styles.dayMeta}>{day.meta}</Text> : null}
              </View>
              <View style={{ gap: 8 }}>
                {day.clips.map((clip, i) => (
                  <RiseIn key={clip.id} delay={i * 55}>
                    <ClipRow clip={clip} />
                  </RiseIn>
                ))}
              </View>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bgScreen },
  search: {
    height: 42,
    borderRadius: 14,
    backgroundColor: 'rgba(245,243,255,.05)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.08)',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    paddingHorizontal: 13,
  },
  searchInput: {
    flex: 1,
    fontSize: 14,
    fontFamily: fonts.ui,
    color: colors.textPrimary,
    paddingVertical: 0,
  },
  body: { paddingHorizontal: 16, gap: 16 },
  ribbonInner: { paddingTop: 15, paddingBottom: 14, gap: 12 },
  ribbonHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  ribbonMeta: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.textMuted,
  },
  ribbonBars: {
    height: 46,
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 4,
  },
  bar: {
    flex: 1,
    height: '62%',
    borderRadius: 3,
    backgroundColor: 'rgba(139,124,246,.45)',
  },
  barLive: { height: '100%', backgroundColor: colors.accentAmber },
  ribbonEmpty: {
    height: 72,
    borderRadius: 12,
    backgroundColor: 'rgba(245,243,255,.03)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.06)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  ribbonEmptyText: {
    fontSize: 12,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  chip: {
    height: 31,
    paddingHorizontal: 13,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(245,243,255,.04)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.08)',
  },
  chipOn: {
    backgroundColor: 'rgba(139,124,246,.16)',
    borderColor: 'rgba(139,124,246,.42)',
  },
  chipText: {
    fontSize: 12,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
  },
  chipOnText: {
    fontSize: 12,
    fontFamily: fonts.uiSemi,
    color: colors.textAccentSoft,
  },
  dayHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  dayMeta: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.textMuted,
  },
  emptyList: {
    paddingTop: 36,
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
    maxWidth: 280,
  },
});
