import { StyleSheet, View, ViewProps } from 'react-native';

import { colors } from '@/constants/theme';

type Props = ViewProps & { children: React.ReactNode; innerStyle?: ViewProps['style'] };

/**
 * Secondary card — the two-layer construction used by the Clips ribbon and the
 * Remote peers / NAS offload cards in the mockup:
 *
 *   outer  1px rgba(245,243,255,.07) on rgba(245,243,255,.025), radius 22, pad 4
 *   inner  #181428, radius 18, inset 0 1px 0 rgba(245,243,255,.06)
 *
 * Elevation is the lightness step plus the inset highlight — never a shadow.
 */
export function SoftCard({ children, style, innerStyle, ...rest }: Props) {
  return (
    <View style={[styles.outer, style]} {...rest}>
      <View style={[styles.inner, innerStyle]}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: {
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.rowBorder,
    backgroundColor: colors.bgCardSoft,
    padding: 4,
  },
  inner: {
    backgroundColor: colors.bgCard,
    borderRadius: 18,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.softCardInset,
    paddingVertical: 13,
    paddingHorizontal: 16,
    gap: 12,
  },
});
