import React from 'react';
import { Text, TextProps } from 'react-native';
import { colors, fontFamilies, typescale } from '@/constants/theme';

interface LargeTitleProps extends TextProps {
  children: React.ReactNode;
  variant?: 'default' | 'classify';
}

/**
 * Large title for Clips, Remote, Games, Appearance screens.
 * Default: 32px/700. Classify variant: 27px/700.
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
          fontWeight: scale.fontWeight as any,
          lineHeight: scale.fontSize * scale.lineHeight,
          letterSpacing: scale.letterSpacing * 0.01, // Normalize for RN
          color: colors.textPrimary,
          fontFamily: fontFamilies.ui,
        },
        style,
      ]}
      {...rest}
    >
      {children}
    </Text>
  );
};
