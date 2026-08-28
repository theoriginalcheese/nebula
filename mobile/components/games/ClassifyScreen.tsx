import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { AmbientBackdrop } from '@/components/ui/AmbientBackdrop';
import { Eyebrow } from '@/components/ui/Eyebrow';
import { colors, fonts } from '@/constants/theme';
import { useStudio } from '@/state/StudioContext';
import type { ClassifyIcon, ClassifyItem } from '@/state/studio';

const TAB_CLEAR = 110;

function GameIcon({ icon }: { icon: ClassifyIcon }) {
  switch (icon) {
    case 'sifu':
      return (
        <Svg width={26} height={26} viewBox="0 0 24 24" fill="none" stroke="#A8DBF6" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
          <Path d="M19.2 4.8 9.4 14.6" />
          <Path d="M15.2 4.6h4.4v4.4" />
          <Path d="M8 16l-3.4 3.4M4.6 15.6 8.4 19.4" />
        </Svg>
      );
    case 'blender':
      return (
        <Svg width={26} height={26} viewBox="0 0 24 24" fill="none" stroke="#F6DCB6" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
          <Path d="M12 3.4 20 7.8v8.4L12 20.6 4 16.2V7.8z" />
          <Path d="M4 7.8 12 12.3l8-4.5M12 12.3v8.3" />
        </Svg>
      );
    case 'yakuza0':
      return (
        <Svg width={26} height={26} viewBox="0 0 24 24" fill="none" stroke="#EFB8F5" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
          <Circle cx="12" cy="12" r="8.4" />
          <Path d="M12 6.6 15.4 12 12 17.4 8.6 12z" />
        </Svg>
      );
  }
}

/** fullscreen state, input device, GPU load, store-library membership, window-chrome */
function SignalIcon({ index, stroke }: { index: number; stroke: string }) {
  const common = { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke, strokeWidth: 1.9, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  switch (index) {
    case 0:
      return (
        <Svg {...common}>
          <Rect x="3.4" y="5" width="17.2" height="12" rx="2" />
          <Path d="M9 20h6" />
        </Svg>
      );
    case 1:
      return (
        <Svg {...common}>
          <Rect x="2.6" y="7.4" width="18.8" height="9.2" rx="4.6" />
          <Path d="M7.6 10.6v3.2M6 12.2h3.2M15.6 11.6h.01M17.8 13.4h.01" />
        </Svg>
      );
    case 2:
      return (
        <Svg {...common}>
          <Path d="M3.6 16.4 8 9.6l3.6 4 3-5.2 4.2 8" />
        </Svg>
      );
    case 3:
      return (
        <Svg {...common}>
          <Path d="M4 6.4h16v13.2H4z" />
          <Path d="M8.4 6.4V4.4h7.2v2" />
        </Svg>
      );
    default:
      return (
        <Svg {...common}>
          <Rect x="3.4" y="4.6" width="17.2" height="14.8" rx="2" />
          <Path d="M3.4 9h17.2" />
        </Svg>
      );
  }
}

export function ClassifyScreen({ id }: { id: string }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { state, decideClassify, skipClassify } = useStudio();

  const index = state.classifyQueue.findIndex((i) => i.id === id);
  const item: ClassifyItem | undefined =
    index >= 0 ? state.classifyQueue[index] : state.classifyQueue[0];
  const total = state.classifyQueue.length;
  const position = item ? Math.max(1, (index >= 0 ? index : 0) + 1) : 0;

  const decide = () => {
    if (!item) return;
    decideClassify(item.id);
    router.back();
  };

  const skip = () => {
    if (!item) return;
    skipClassify(item.id);
    router.back();
  };

  return (
    <View style={styles.screen}>
      <AmbientBackdrop variant="games" />
      <View style={[styles.header, { paddingTop: insets.top + 2 }]}>
        <Pressable onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="#B9AEF9" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round">
            <Path d="m14.5 5-7 7 7 7" />
          </Svg>
        </Pressable>
        <Text style={styles.title}>Classify</Text>
        {item ? (
          <View style={styles.posPill}>
            <Text style={styles.posText}>
              {position} / {total}
            </Text>
          </View>
        ) : null}
      </View>

      {!item ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>Queue clear</Text>
          <Text style={styles.emptyBody}>
            Nothing left to classify. New detections land here as the studio agent sees them.
          </Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={[styles.body, { paddingBottom: TAB_CLEAR + insets.bottom }]}
          showsVerticalScrollIndicator={false}>
          <View style={styles.itemOuter}>
            <View style={styles.itemInner}>
              <View style={[styles.itemTile, { backgroundColor: item.tint }]}>
                <GameIcon icon={item.icon} />
              </View>
              <View style={{ flex: 1, gap: 5, minWidth: 0 }}>
                <Text style={styles.itemName} numberOfLines={1}>
                  {item.name}
                </Text>
                <Text style={styles.itemExe} numberOfLines={1}>
                  {item.exe}
                </Text>
                <Text style={styles.itemPub} numberOfLines={1}>
                  {item.publisher}
                </Text>
              </View>
            </View>
          </View>

          <View style={styles.signalsOuter}>
            <View style={styles.signalsInner}>
              <View style={styles.signalsHead}>
                <Eyebrow>What Nebula saw</Eyebrow>
                <Text style={styles.votes}>
                  {item.signals.filter((s) => s.lean === 'game').length} of 5 lean game
                </Text>
              </View>

              <View style={{ gap: 10 }}>
                {item.signals.map((signal, i) => {
                  const leansGame = signal.lean === 'game';
                  return (
                    <View key={i} style={styles.signalRow}>
                      <View
                        style={[
                          styles.signalDot,
                          leansGame
                            ? { backgroundColor: 'rgba(139,124,246,.2)', shadowColor: colors.accentDefault }
                            : { backgroundColor: 'rgba(245,243,255,.06)' },
                        ]}>
                        <SignalIcon index={i} stroke={leansGame ? '#B9AEF9' : '#8B84B8'} />
                      </View>
                      <Text style={styles.signalText}>{signal.text}</Text>
                    </View>
                  );
                })}
              </View>

              <View style={styles.rule} />

              <View style={styles.verdictRow}>
                {item.warn ? (
                  <View style={styles.warnDot}>
                    <Svg width={11} height={11} viewBox="0 0 24 24" fill="none" stroke={colors.accentAmber} strokeWidth={2.1} strokeLinecap="round">
                      <Path d="M12 7.6v5.2M12 16.6h.01" />
                    </Svg>
                  </View>
                ) : null}
                <Text style={styles.verdictText}>
                  {item.verdictLabel}, so Nebula is asking instead of guessing.
                </Text>
              </View>
            </View>
          </View>

          <View style={styles.actions}>
            <Pressable
              onPress={decide}
              style={({ pressed }) => [styles.actionPrimary, pressed && { transform: [{ scale: 0.97 }] }]}>
              <Svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke={colors.textPrimary} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
                <Rect x="2.6" y="7.4" width="18.8" height="9.2" rx="4.6" />
                <Path d="M7.6 10.6v3.2M6 12.2h3.2" />
              </Svg>
              <Text style={styles.actionPrimaryLabel}>It is a game</Text>
            </Pressable>
            <Pressable
              onPress={decide}
              style={({ pressed }) => [styles.actionSecondary, pressed && { transform: [{ scale: 0.97 }] }]}>
              <Svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke={colors.textAccentSoft} strokeWidth={1.8} strokeLinecap="round">
                <Path d="M6 6l12 12M6 18 18 6" />
              </Svg>
              <Text style={styles.actionSecondaryLabel}>Not a game</Text>
            </Pressable>
          </View>

          <Pressable onPress={skip} style={({ pressed }) => [styles.skip, pressed && { transform: [{ scale: 0.97 }] }]}>
            <Svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke={colors.textLabel} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
              <Circle cx="12" cy="12" r="8.4" />
              <Path d="M12 7.8V12l3 1.8" />
            </Svg>
            <Text style={styles.skipLabel}>Skip for now</Text>
          </Pressable>

          <View style={{ gap: 9 }}>
            <Eyebrow>Decided today</Eyebrow>
            <Text style={styles.decidedLine}>
              {state.decidedToday} settled. Every answer trains the local classifier, so an
              executable is never asked about twice.
            </Text>
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bgScreen },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 20,
    paddingBottom: 14,
  },
  back: {
    width: 30,
    height: 30,
    borderRadius: 999,
    backgroundColor: 'rgba(245,243,255,.05)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    flex: 1,
    fontSize: 27,
    fontFamily: fonts.uiBold,
    letterSpacing: -0.81,
    color: colors.textPrimary,
  },
  posPill: {
    height: 26,
    paddingHorizontal: 11,
    borderRadius: 999,
    backgroundColor: 'rgba(245,166,35,.12)',
    borderWidth: 1,
    borderColor: 'rgba(245,166,35,.28)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  posText: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.accentAmber,
  },
  body: { paddingHorizontal: 16, gap: 13 },
  itemOuter: {
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.07)',
    backgroundColor: 'rgba(245,243,255,.025)',
    padding: 5,
  },
  itemInner: {
    backgroundColor: colors.bgCard,
    borderRadius: 19,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(245,243,255,.07)',
    paddingVertical: 18,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 15,
  },
  itemTile: {
    width: 54,
    height: 54,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  itemName: {
    fontSize: 20,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.4,
    color: colors.textPrimary,
  },
  itemExe: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.textLabel,
  },
  itemPub: {
    fontSize: 11.5,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  signalsOuter: {
    borderRadius: 22,
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.07)',
    backgroundColor: 'rgba(245,243,255,.025)',
    padding: 4,
  },
  signalsInner: {
    backgroundColor: colors.bgCard,
    borderRadius: 18,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(245,243,255,.06)',
    paddingVertical: 15,
    paddingHorizontal: 16,
    gap: 13,
  },
  signalsHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  votes: {
    fontFamily: fonts.mono,
    fontSize: 10,
    color: colors.textMuted,
  },
  signalRow: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  signalDot: {
    width: 24,
    height: 24,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  signalText: {
    flex: 1,
    fontSize: 12.5,
    fontFamily: fonts.ui,
    color: '#C5BFDE',
  },
  rule: { height: 1, backgroundColor: 'rgba(245,243,255,.11)' },
  verdictRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  warnDot: {
    width: 20,
    height: 20,
    borderRadius: 999,
    backgroundColor: 'rgba(245,166,35,.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  verdictText: {
    flex: 1,
    fontSize: 12,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
  },
  actions: { flexDirection: 'row', gap: 10 },
  actionPrimary: {
    flex: 1,
    height: 56,
    borderRadius: 999,
    backgroundColor: 'rgba(139,124,246,.32)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.09)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 9,
  },
  actionPrimaryLabel: {
    fontSize: 14,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.14,
    color: colors.textPrimary,
  },
  actionSecondary: {
    flex: 1,
    height: 56,
    borderRadius: 999,
    backgroundColor: 'rgba(245,243,255,.045)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.11)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 9,
  },
  actionSecondaryLabel: {
    fontSize: 14,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.14,
    color: colors.textAccentSoft,
  },
  skip: {
    height: 44,
    borderRadius: 999,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  skipLabel: {
    fontSize: 12.5,
    fontFamily: fonts.ui,
    color: colors.textLabel,
  },
  decidedLine: {
    fontSize: 12,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 32,
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
  },
});
