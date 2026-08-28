import { View, ViewProps } from 'react-native';

import { colors, radii, cardStyles } from '@/constants/theme';

type Props = ViewProps & {
  children: React.ReactNode;
  variant?: 'default' | 'soft';
  inset?: boolean;
};

/** Card surface — lightness step + inset highlight, no drop shadow. */
export function NebulaCard({ children, variant = 'default', inset = true, style, ...rest }: Props) {
  return (
    <View
      style={[
        {
          backgroundColor: variant === 'soft' ? colors.bgCardSoft : colors.bgCard,
          borderRadius: radii.card,
          overflow: 'hidden',
          ...(variant === 'soft'
            ? { borderWidth: 1, borderColor: colors.bgCardSoftBorder }
            : null),
        },
        inset && cardStyles.insetHighlight,
        style,
      ]}
      {...rest}>
      {children}
    </View>
  );
}
