import React from 'react';
import {
  Pressable,
  PressableProps,
  Text,
  View,
} from 'react-native';
import { colors, radii, motion, fontFamilies, typescale } from '@/constants/theme';

interface PillButtonProps extends Omit<PressableProps, 'children'> {
  label: string;
  variant?: 'primary' | 'secondary' | 'tertiary';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
}

/**
 * Pill button with scale press feedback (0.97 on active).
 * Three variants: primary (accent), secondary (muted), tertiary (text only).
 */
export const PillButton: React.FC<PillButtonProps> = ({
  label,
  variant = 'secondary',
  size = 'md',
  icon,
  style,
  onPressIn,
  onPressOut,
  ...rest
}) => {
  const [pressed, setPressed] = React.useState(false);

  const sizeStyles = {
    sm: { paddingHorizontal: 12, paddingVertical: 8, gap: 8 },
    md: { paddingHorizontal: 16, paddingVertical: 10, gap: 10 },
    lg: { paddingHorizontal: 20, paddingVertical: 12, gap: 12 },
  };

  const variantStyles = {
    primary: {
      backgroundColor: colors.accentDefault,
      borderColor: colors.accentDefault,
    },
    secondary: {
      backgroundColor: 'rgba(245,243,255,.05)',
      borderColor: 'rgba(245,243,255,.13)',
    },
    tertiary: {
      backgroundColor: 'transparent',
      borderColor: 'transparent',
    },
  };

  const textColor = {
    primary: colors.textPrimary,
    secondary: colors.textSecondary,
    tertiary: colors.textSecondary,
  };

  return (
    <Pressable
      onPressIn={(e) => {
        setPressed(true);
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        setPressed(false);
        onPressOut?.(e);
      }}
      style={(state) => [
        {
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          ...sizeStyles[size],
          borderRadius: radii.pill,
          borderWidth: 1,
          ...variantStyles[variant],
          transform: [{ scale: state.pressed || pressed ? motion.pressScale.pill : 1 }],
        },
        typeof style === 'function' ? style(state) : style,
      ]}
      {...rest}
    >
      {icon && <View style={{ marginRight: 4 }}>{icon}</View>}
      <Text
        style={{
          fontSize: typescale.body.fontSize,
          fontWeight: typescale.body.fontWeight as any,
          color: textColor[variant],
          fontFamily: fontFamilies.ui,
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
};
