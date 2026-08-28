import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { ScreenHeader } from '@/components/ScreenHeader';
import { AmbientBackdrop } from '@/components/ui/AmbientBackdrop';
import { Eyebrow } from '@/components/ui/Eyebrow';
import { OrbitDust } from '@/components/ui/OrbitDust';
import { colors, fonts } from '@/constants/theme';
import { useStudio } from '@/state/StudioContext';

const TAB_CLEAR = 110;

/** Moonlight states scaffolded — default Ready with honest unpaired copy. */
type MoonState = 'ready' | 'busy' | 'live';

export function RemoteScreen() {
  const insets = useSafeAreaInsets();
  const { state, motionScale } = useStudio();
  const moon: MoonState = 'ready';
  const studioOnline = state.connection === 'online';

  const title =
    moon === 'live'
      ? 'Streaming'
      : moon === 'busy'
        ? 'Handshaking…'
        : studioOnline
          ? 'Studio PC is awake'
          : 'Studio PC';

  const body =
    moon === 'live'
      ? 'Stream metrics appear once Moonlight reports a live session.'
      : moon === 'busy'
        ? 'Negotiating the encoder over the tailnet. This is usually under two seconds.'
        : studioOnline
          ? 'Moonlight pairing isn’t confirmed yet. Launch opens the Moonlight app when installed.'
          : 'Waiting for the studio Tailscale link. Orb and peers stay empty until the agent reports them.';

  const cta =
    moon === 'live' ? 'Stop streaming' : moon === 'busy' ? 'Connecting…' : 'Launch Moonlight';

  return (
    <View style={styles.screen}>
      <AmbientBackdrop variant="remote" />
      <View style={{ paddingTop: insets.top }}>
        <ScreenHeader variant="large-title" title="Remote" />
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: TAB_CLEAR + insets.bottom }]}
        showsVerticalScrollIndicator={false}>
        <LinearGradient
          colors={['rgba(139,124,246,0.08)', 'rgba(245,243,255,0.02)']}
          start={{ x: 0.15, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.moonOuter}>
          <View style={styles.moonInner}>
            <View style={styles.orbWrap}>
              <View style={styles.orbGlow} />
              <View style={styles.orbRing1} />
              <View style={styles.orbRing2} />
              <OrbitDust colour="#C9BFFF" motionScale={motionScale} size={118} />
              <View
                style={[
                  styles.orbCore,
                  moon === 'live' && { backgroundColor: 'rgba(245,166,35,.55)' },
                  moon === 'busy' && { backgroundColor: 'rgba(139,124,246,.7)' },
                ]}
              />
            </View>

            <View style={{ gap: 7, alignItems: 'center' }}>
              <Text style={styles.moonTitle}>{title}</Text>
              <Text style={styles.moonBody}>{body}</Text>
            </View>

            <Pressable
              disabled={moon === 'busy'}
              style={({ pressed }) => [
                styles.cta,
                pressed && moon !== 'busy' && { transform: [{ scale: 0.97 }] },
                moon === 'busy' && { opacity: 0.7 },
              ]}>
              <Text style={styles.ctaLabel}>{cta}</Text>
              <View style={styles.ctaIcon}>
                {moon === 'live' ? (
                  <Svg width={17} height={17} viewBox="0 0 24 24">
                    <Rect x="6.2" y="6.2" width="11.6" height="11.6" rx="2.6" fill={colors.goldText} />
                  </Svg>
                ) : moon === 'busy' ? (
                  <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
                    <Path
                      d="M12 4v3.4M12 16.6V20M4 12h3.4M16.6 12H20M6.6 6.6l2.4 2.4M15 15l2.4 2.4M17.4 6.6 15 9M9 15l-2.4 2.4"
                      stroke={colors.textPrimary}
                      strokeWidth={1.8}
                      strokeLinecap="round"
                      opacity={0.85}
                    />
                  </Svg>
                ) : (
                  <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
                    <Path
                      d="M4 8.4a12 12 0 0 1 16 0M7.2 12.2a7.4 7.4 0 0 1 9.6 0"
                      stroke={colors.textPrimary}
                      strokeWidth={1.7}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <Circle cx="12" cy="16.6" r="1.6" fill={colors.textPrimary} />
                  </Svg>
                )}
              </View>
            </Pressable>
          </View>
        </LinearGradient>

        <View style={styles.cardOuter}>
          <View style={styles.cardInner}>
            <View style={styles.cardHead}>
              <View style={styles.tealDot} />
              <Eyebrow>Tailscale</Eyebrow>
              <Text style={styles.cardCount}>— peers</Text>
            </View>
            <LinearGradient
              colors={['transparent', 'rgba(245,243,255,0.11)', 'rgba(245,243,255,0.11)', 'transparent']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={styles.rule}
            />
            <Text style={styles.emptyLine}>No peers reported yet</Text>
          </View>
        </View>

        <View style={styles.cardOuter}>
          <View style={styles.cardInner}>
            <View style={styles.offloadHead}>
              <Eyebrow>NAS offload</Eyebrow>
              <Text style={styles.offloadCount}>idle</Text>
            </View>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: '0%' }]} />
            </View>
            <Text style={styles.emptyLine}>Nothing queued</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bgScreen },
  body: { paddingHorizontal: 16, gap: 12 },
  moonOuter: {
    borderRadius: 26,
    borderWidth: 1,
    borderColor: 'rgba(139,124,246,.24)',
    padding: 5,
  },
  moonInner: {
    backgroundColor: colors.bgCard,
    borderRadius: 21,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(245,243,255,.08)',
    paddingVertical: 16,
    paddingHorizontal: 20,
    alignItems: 'center',
    gap: 18,
  },
  orbWrap: {
    width: 118,
    height: 118,
    alignItems: 'center',
    justifyContent: 'center',
  },
  orbGlow: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 999,
    backgroundColor: 'rgba(139,124,246,.34)',
    opacity: 0.55,
  },
  orbRing1: {
    position: 'absolute',
    top: 14,
    left: 14,
    right: 14,
    bottom: 14,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'rgba(139,124,246,.34)',
  },
  orbRing2: {
    position: 'absolute',
    top: 30,
    left: 30,
    right: 30,
    bottom: 30,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'rgba(139,124,246,.22)',
  },
  orbCore: {
    width: 56,
    height: 56,
    borderRadius: 999,
    backgroundColor: 'rgba(139,124,246,.55)',
  },
  moonTitle: {
    fontSize: 21,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.42,
    color: colors.textPrimary,
    textAlign: 'center',
  },
  moonBody: {
    fontSize: 13,
    lineHeight: 21,
    fontFamily: fonts.ui,
    color: colors.textSecondary,
    maxWidth: 250,
    textAlign: 'center',
  },
  cta: {
    width: '100%',
    height: 58,
    borderRadius: 999,
    backgroundColor: 'rgba(139,124,246,.42)',
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.09)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingLeft: 24,
    paddingRight: 8,
  },
  ctaLabel: {
    fontSize: 15.5,
    fontFamily: fonts.uiSemi,
    letterSpacing: -0.155,
    color: colors.textPrimary,
  },
  ctaIcon: {
    width: 42,
    height: 42,
    borderRadius: 999,
    backgroundColor: 'rgba(245,243,255,.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardOuter: {
    borderRadius: 22,
    borderWidth: 1,
    borderColor: 'rgba(245,243,255,.07)',
    backgroundColor: 'rgba(245,243,255,.025)',
    padding: 4,
  },
  cardInner: {
    backgroundColor: colors.bgCard,
    borderRadius: 18,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(245,243,255,.06)',
    paddingVertical: 13,
    paddingHorizontal: 16,
    gap: 12,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  tealDot: {
    width: 6,
    height: 6,
    borderRadius: 999,
    backgroundColor: colors.accentTeal,
  },
  cardCount: {
    marginLeft: 'auto',
    fontFamily: fonts.mono,
    fontSize: 10,
    color: colors.textMuted,
  },
  rule: { height: 1, width: '100%' },
  emptyLine: {
    fontSize: 13,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  offloadHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  offloadCount: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.textAccentSoft,
  },
  progressTrack: {
    height: 3,
    borderRadius: 999,
    backgroundColor: 'rgba(245,243,255,.08)',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.accentDefault,
  },
});
