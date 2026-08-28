import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path } from 'react-native-svg';

import { ScreenHeader } from '@/components/ScreenHeader';
import { AmbientBackdrop } from '@/components/ui/AmbientBackdrop';
import { Eyebrow } from '@/components/ui/Eyebrow';
import { colors, fonts } from '@/constants/theme';

const TAB_CLEAR = 110;

export function ClipsScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.screen}>
      <AmbientBackdrop variant="clips" />
      <View style={{ paddingTop: insets.top }}>
        <ScreenHeader variant="large-title" title="Clips">
          <View style={styles.search}>
            <Svg width={15} height={15} viewBox="0 0 24 24" fill="none">
              <Circle cx="11" cy="11" r="6.4" stroke="#736BA4" strokeWidth={1.6} />
              <Path d="m16 16 4 4" stroke="#736BA4" strokeWidth={1.6} strokeLinecap="round" />
            </Svg>
            <TextInput
              placeholder="Search clips"
              placeholderTextColor="#736BA4"
              style={styles.searchInput}
              editable={false}
            />
          </View>
        </ScreenHeader>
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: TAB_CLEAR + insets.bottom }]}
        showsVerticalScrollIndicator={false}>
        <View style={styles.ribbonOuter}>
          <View style={styles.ribbonInner}>
            <View style={styles.ribbonHead}>
              <Eyebrow>Today</Eyebrow>
              <Text style={styles.ribbonMeta}>—</Text>
            </View>
            <View style={styles.ribbonEmpty}>
              <Text style={styles.ribbonEmptyText}>No session activity yet</Text>
            </View>
          </View>
        </View>

        <View style={styles.chips}>
          <View style={[styles.chip, styles.chipOn]}>
            <Text style={styles.chipOnText}>All</Text>
          </View>
        </View>

        <View style={styles.emptyList}>
          <Text style={styles.emptyTitle}>No clips yet</Text>
          <Text style={styles.emptyBody}>
            Day-grouped recordings appear here once the studio link syncs clip metadata.
          </Text>
        </View>
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
  ribbonOuter: {
    borderRadius: 22,
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.07)',
    backgroundColor: 'rgba(245,243,255,.025)',
    padding: 4,
  },
  ribbonInner: {
    backgroundColor: colors.bgCard,
    borderRadius: 18,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(245,243,255,.06)',
    paddingTop: 15,
    paddingHorizontal: 16,
    paddingBottom: 14,
    gap: 12,
  },
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
    borderColor: 'rgba(245,243,255,.1)',
  },
  chipOn: {
    backgroundColor: 'rgba(139,124,246,.2)',
    borderColor: 'rgba(139,124,246,.4)',
  },
  chipOnText: {
    fontSize: 12,
    fontFamily: fonts.uiSemi,
    color: colors.textAccentSoft,
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
