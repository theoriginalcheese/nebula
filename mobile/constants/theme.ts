/**
 * Nebula Mobile design tokens — BUILD-SPEC + Nebula Mobile.dc.html
 */

import {
  PlusJakartaSans_500Medium,
  PlusJakartaSans_600SemiBold,
  PlusJakartaSans_700Bold,
} from '@expo-google-fonts/plus-jakarta-sans';
import {
  JetBrainsMono_500Medium,
  JetBrainsMono_700Bold,
} from '@expo-google-fonts/jetbrains-mono';

export const colors = {
  bgPage: '#0A0812',
  bgScreen: '#100D1C',
  bgCard: '#181428',
  bgCardSoft: 'rgba(245,243,255,0.025)',
  bgCardSoftBorder: 'rgba(245,243,255,0.07)',
  textPrimary: '#F5F3FF',
  textSecondary: '#9A93C4',
  textMuted: '#8B84B8',
  textLabel: '#736BA4',
  textAccentSoft: '#C9BFFF',
  textStudio: '#B9AEF9',
  accentDefault: '#8B7CF6',
  accentIndigo: '#6E8BF7',
  accentCyan: '#5AB6E8',
  accentTeal: '#4FC7B8',
  accentAmber: '#F5A623',
  accentAmberPicker: '#E9B872',
  accentMagenta: '#D471E0',
  danger: '#FF5C7A',
  dangerText: '#FFD3DC',
  dangerOffline: '#FF9DB0',
  dangerLabel: '#FFB3C2',
  goldText: '#FFE8BC',
  tabBarBg: 'rgba(18,16,31,0.72)',
  tabBarBorder: 'rgba(245,243,255,0.08)',
  cardInset: 'rgba(245,243,255,0.08)',
  recordingBorder: 'rgba(245,166,35,0.2)',
  recordingGlow: 'rgba(245,166,35,0.07)',
  toastBg: 'rgba(10,8,18,0.92)',
  toastBorder: 'rgba(139,124,246,0.34)',
  toastIconBg: 'rgba(139,124,246,0.18)',
  toastIconBorder: 'rgba(139,124,246,0.38)',
  violetGlow: 'rgba(139,124,246,0.34)',
  softCardInset: 'rgba(245,243,255,0.06)',
  rowFill: 'rgba(245,243,255,0.03)',
  rowBorder: 'rgba(245,243,255,0.07)',
  toggleOnTrack: 'rgba(139,124,246,0.5)',
  toggleOnBorder: 'rgba(139,124,246,0.7)',
  toggleOffTrack: 'rgba(245,243,255,0.07)',
  toggleOffBorder: 'rgba(245,243,255,0.12)',
  peerPing: '#8FE0D5',
  amberGlow: 'rgba(245,166,35,0.13)',
} as const;

/** Legacy alias */
export const colours = colors;

/**
 * The six accent presets, carried over verbatim from the desktop app.
 * EMBER (the desktop's disconnected red) is deliberately absent — one token,
 * one meaning, so a real disconnection still reads as one.
 */
export const accentPresets = [
  { id: 'violet', hex: '#8B7CF6', soft: '#B9AEF9', rgb: '139,124,246' },
  { id: 'indigo', hex: '#6E8BF7', soft: '#A6BAFB', rgb: '110,139,247' },
  { id: 'cyan', hex: '#5AB6E8', soft: '#9AD3F2', rgb: '90,182,232' },
  { id: 'teal', hex: '#4FC7B8', soft: '#8FE0D5', rgb: '79,199,184' },
  { id: 'amber', hex: '#E9B872', soft: '#F2D2A4', rgb: '233,184,114' },
  { id: 'magenta', hex: '#D471E0', soft: '#E7A9EE', rgb: '212,113,224' },
] as const;

export type AccentId = (typeof accentPresets)[number]['id'];

export const fontAssets = {
  PlusJakartaSans_500Medium,
  PlusJakartaSans_600SemiBold,
  PlusJakartaSans_700Bold,
  JetBrainsMono_500Medium,
  JetBrainsMono_700Bold,
} as const;

export const fonts = {
  ui: 'PlusJakartaSans_500Medium',
  uiSemi: 'PlusJakartaSans_600SemiBold',
  uiBold: 'PlusJakartaSans_700Bold',
  mono: 'JetBrainsMono_500Medium',
  monoBold: 'JetBrainsMono_700Bold',
} as const;

/** Legacy alias used across components */
export const fontFamilies = fonts;

export const ease = 'cubic-bezier(0.32, 0.72, 0, 1)';

export const typescale = {
  largeTitle: { fontSize: 32, fontWeight: '700' as const, lineHeight: 34, letterSpacing: -1.024 },
  /** Classify header — 27px/700, dc.html #f-classify */
  classifyTitle: { fontSize: 27, fontWeight: '700' as const, lineHeight: 30, letterSpacing: -0.81 },
  navTitle: { fontSize: 17, fontWeight: '600' as const, letterSpacing: -0.015 * 17 },
  heading: { fontSize: 23, fontWeight: '600' as const, lineHeight: 26, letterSpacing: -0.5 },
  body: { fontSize: 12, fontWeight: '400' as const, lineHeight: 18 },
  meta: { fontSize: 11.5, fontWeight: '500' as const, lineHeight: 16 },
  small: { fontSize: 10.5, fontWeight: '400' as const },
  eyebrow: {
    fontSize: 9.5,
    fontWeight: '600' as const,
    letterSpacing: 2.1,
    textTransform: 'uppercase' as const,
  },
  tabLabel: { fontSize: 9.5, fontWeight: '600' as const, letterSpacing: 0.19 },
  tabLabelInactive: { fontSize: 9.5, fontWeight: '500' as const, letterSpacing: 0.19 },
  mono: { fontSize: 14, fontWeight: '400' as const },
  monoSmall: { fontSize: 10.5, fontWeight: '400' as const },
  monoClock: { fontSize: 44, fontWeight: '400' as const, letterSpacing: -1.3, lineHeight: 44 },
} as const;

export const spacing = { xs: 4, sm: 7, md: 11, lg: 16, xl: 20, xxl: 26 } as const;

export const radii = {
  pill: 999,
  card: 21,
  cardOuter: 26,
  cardLarge: 26,
  icon: 22,
  tabBar: 26,
  toast: 18,
} as const;

export const motion = {
  pressPill: 0.97,
  pressCircle: 0.94,
  pressScale: { pill: 0.97, circle: 0.94 },
  tabColourMs: 400,
  defaultScale: 1,
} as const;

export const layout = {
  tabBar: {
    height: 64,
    marginHorizontal: 14,
    marginBottom: 26,
    borderRadius: 26,
    shadow: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 12 },
      shadowOpacity: 0.5,
      shadowRadius: 34,
      elevation: 16,
    },
  },
  screenPaddingH: 16,
} as const;

export const cardStyles = {
  outerRecording: {
    borderRadius: radii.cardOuter,
    borderWidth: 1,
    borderColor: colors.recordingBorder,
    backgroundColor: colors.recordingGlow,
    padding: 5,
  },
  inner: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.card,
    borderTopWidth: 1,
    borderTopColor: colors.cardInset,
  },
  insetHighlight: {
    borderTopWidth: 1,
    borderTopColor: colors.cardInset,
  },
} as const;
