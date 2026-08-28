import React from 'react';
import { View, ViewProps } from 'react-native';
import { colors, radii } from '@/constants/theme';

interface InsetSurfaceProps extends ViewProps {
  children: React.ReactNode;
  variant?: 'default' | 'soft';
}

/**
 * Inset surface with border and subtle background.
 * Used for cards with visible border (e.g., recording card border).
 */
export const InsetSurface: React.FC<InsetSurfaceProps> = ({
  children,
  variant = 'default',
  style,
  ...rest
}) => {
  const borderColor = variant === 'soft'
    ? colors.bgCardSoftBorder
    : 'rgba(245,166,35,.2)'; // Gold border for recording card

  return (
    <View
      style={[
        {
          borderRadius: radii.cardOuter,
          borderWidth: 1,
          borderColor,
          padding: variant === 'soft' ? 8 : 5,
          backgroundColor: 'transparent',
        },
        style,
      ]}
      {...rest}
    >
      {children}
    </View>
  );
};
