import React from 'react';
import { Text, TextProps } from 'react-native';

import { colors, fonts, typescale } from '@/constants/theme';

interface LargeTitleProps extends TextProps {
  children: React.ReactNode;
  variant?: 'default' | 'classify';
}

/**
 * Large title for Clips, Remote, Games, Appearance screens.
 * Default: 32px/700 (dc.html large-title frames).
 * Classify variant: 27px/700 (dc.html #f-classify header).
 */
export const LargeTitle: React.FC<LargeTitleProps> = ({
  children,
  variant = 'default',
  style,
  ...rest
}) => {
  const scale = variant === 'classify' ? typescale.classifyTitle : typescale.largeTitle;

  return (
    <Text
      style={[
        {
          fontSize: scale.fontSize,
          lineHeight: scale.lineHeight,
          letterSpacing: scale.letterSpacing,
          color: colors.textPrimary,
          fontFamily: fonts.uiBold,
        },
        style,
      ]}
      {...rest}>
      {children}
    </Text>
  );
};
