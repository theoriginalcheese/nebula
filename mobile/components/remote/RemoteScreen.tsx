import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { MoonlightOrb } from '@/components/remote/MoonlightOrb';
import { ScreenHeader } from '@/components/ScreenHeader';
import { AmbientBackdrop } from '@/components/ui/AmbientBackdrop';
import { Eyebrow } from '@/components/ui/Eyebrow';
import { FadeRule } from '@/components/ui/FadeRule';
import { RiseIn } from '@/components/ui/RiseIn';
import { SoftCard } from '@/components/ui/SoftCard';
import { colors, fonts } from '@/constants/theme';

import { useStudio } from '@/state/StudioContext';

const TAB_CLEAR = 110;

export function RemoteScreen() {
  const insets = useSafeAreaInsets();
  const { state, motionScale, moonlightNotice, launchMoonlight } = useStudio();
  const moon = state.moonlight;
  const studioOnline = state.connection === 'online';

  /*
    Ready-state copy depends on what the agent has actually told us. The mockup
    reads "Moonlight 6.1 · GeForce host paired. Stream will open at 1080p60 over
    Tailscale." — that is a live binding, so it only appears once pairing is
    genuinely reported. Live-state metrics (ping, bitrate) arrive by push and
    have no source yet, so the live copy stays metric-free.
  */
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
      ? 'Nebula keeps recording locally at full quality. Stream metrics appear once Moonlight reports them.'
      : moon === 'busy'
        ? 'Negotiating the encoder over the tailnet. This is usually under two seconds.'
        : studioOnline
          ? state.moonlightPaired
            ? 'GeForce host paired. Launch opens the Moonlight app to start the stream.'
            : 'Pairing has not been reported yet. Launch opens the Moonlight app when it is installed.'
          : 'Waiting for the studio Tailscale link. Orb and peers stay empty until the agent reports them.';

  const cta = moon === 'live' ? 'Stop streaming' : moon === 'busy' ? 'Connecting…' : 'Launch Moonlight';

  const onlinePeers = state.peers.filter((p) => p.online).length;
  const offload = state.offload;
  const progress =
    offload && offload.total > 0 ? Math.min(1, offload.done / offload.total) : 0;

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
          colors={
            moon === 'live'
              ? ['rgba(245,166,35,0.08)', 'rgba(245,243,255,0.02)']
              : ['rgba(139,124,246,0.08)', 'rgba(245,243,255,0.02)']
          }
          start={{ x: 0.15, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[styles.moonOuter, moon === 'live' && styles.moonOuterLive]}>
          <View style={styles.moonInner}>
            <MoonlightOrb state={moon} motionScale={motionScale} />

            <View style={{ gap: 7, alignItems: 'center' }}>
              <Text style={styles.moonTitle}>{title}</Text>
              <Text style={styles.moonBody}>{body}</Text>
            </View>

            <Pressable
              accessibilityRole="button"
              disabled={moon === 'busy'}
              onPress={launchMoonlight}
              style={({ pressed }) => [
                styles.cta,
                moon === 'live' && styles.ctaLive,
                pressed && moon !== 'busy' && { transform: [{ scale: 0.97 }] },
                moon === 'busy' && { opacity: 0.7 },
              ]}>
              <Text style={styles.ctaLabel}>{cta}</Text>
              <View style={styles.ctaIcon}>
                {moon === 'live' ? (
                  <Svg width={17} height={17} viewBox="0 0 24 24">
                    <Rect
                      x="6.2"
                      y="6.2"
                      width="11.6"
                      height="11.6"
                      rx="2.6"
                      fill={colors.goldText}
                    />
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

            {moonlightNotice ? <Text style={styles.notice}>{moonlightNotice}</Text> : null}
          </View>
        </LinearGradient>

        <SoftCard>
          <View style={styles.cardHead}>
            <View
              style={[
                styles.headDot,
                { backgroundColor: onlinePeers > 0 ? colors.accentTeal : colors.textLabel },
              ]}
            />
            <Eyebrow>Tailscale</Eyebrow>
            <Text style={styles.cardCount}>
              {state.peers.length > 0 ? `${state.peers.length} peers` : '— peers'}
            </Text>
          </View>
          <FadeRule />
          {state.peers.length === 0 ? (
            <Text style={styles.emptyLine}>No peers reported yet</Text>
          ) : (
            <View style={{ gap: 10 }}>
              {state.peers.map((peer, i) => (
                <RiseIn key={peer.id} delay={i * 55} style={styles.peerRow}>
                  <View
                    style={[
                      styles.peerDot,
                      { backgroundColor: peer.online ? colors.accentTeal : colors.textLabel },
                    ]}
                  />
                  <Text style={[styles.peerName, !peer.online && styles.peerNameOff]}>
                    {peer.name}
                  </Text>
                  <Text style={[styles.peerPing, !peer.online && styles.peerPingOff]}>
                    {peer.online ? (peer.pingMs != null ? `${peer.pingMs} ms` : '—') : 'offline'}
                  </Text>
                </RiseIn>
              ))}
            </View>
          )}
        </SoftCard>

        <SoftCard>
          <View style={styles.offloadHead}>
            <Eyebrow>NAS offload</Eyebrow>
            <Text style={styles.offloadCount}>
              {offload
                ? `${offload.done} of ${offload.total}${offload.sizeLabel ? ` · ${offload.sizeLabel}` : ''}`
                : 'idle'}
            </Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
          </View>
          {offload?.currentFile ? (
            <Text style={styles.offloadFile}>
              {offload.currentFile}
              {offload.throughputLabel ? ` · ${offload.throughputLabel}` : ''}
            </Text>
          ) : (
            <Text style={styles.emptyLine}>Nothing queued</Text>
          )}
        </SoftCard>
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
  moonOuterLive: { borderColor: 'rgba(245,166,35,.26)' },
  moonInner: {
    backgroundColor: colors.bgCard,
    borderRadius: 21,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.cardInset,
    paddingVertical: 16,
    paddingHorizontal: 20,
    alignItems: 'center',
    gap: 18,
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
  ctaLive: { backgroundColor: 'rgba(245,166,35,.34)' },
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
  notice: {
    fontSize: 12,
    lineHeight: 18,
    fontFamily: fonts.ui,
    color: colors.dangerOffline,
    textAlign: 'center',
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  headDot: { width: 6, height: 6, borderRadius: 999 },
  cardCount: {
    marginLeft: 'auto',
    fontFamily: fonts.mono,
    fontSize: 10,
    color: colors.textMuted,
  },
  emptyLine: {
    fontSize: 13,
    fontFamily: fonts.ui,
    color: colors.textMuted,
  },
  peerRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  peerDot: { width: 5, height: 5, borderRadius: 999 },
  peerName: {
    flex: 1,
    fontSize: 13,
    fontFamily: fonts.ui,
    color: colors.textPrimary,
  },
  peerNameOff: { color: colors.textMuted },
  peerPing: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.peerPing,
  },
  peerPingOff: { color: colors.textLabel },
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
  offloadFile: {
    fontFamily: fonts.mono,
    fontSize: 10.5,
    color: colors.textMuted,
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
