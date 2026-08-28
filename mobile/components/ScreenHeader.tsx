import { Text, View, ViewProps } from 'react-native';

import { NebulaMark } from '@/components/ui/NebulaMark';
import { colors, fonts, radii } from '@/constants/theme';

type OnlineDot = 'online' | 'offline' | 'unknown';

type Props = ViewProps & {
  variant?: 'nebula-wordmark' | 'large-title';
  title?: string;
  subtitle?: string;
  subtitleDanger?: boolean;
  onlineDot?: OnlineDot;
  mutedWordmark?: boolean;
};

export function ScreenHeader({
  variant = 'large-title',
  title,
  subtitle,
  subtitleDanger = false,
  onlineDot = 'unknown',
  mutedWordmark = false,
  children,
  style,
  ...rest
}: Props) {
  if (variant === 'nebula-wordmark') {
    const dotColour =
      onlineDot === 'online'
        ? colors.accentDefault
        : onlineDot === 'offline'
          ? colors.danger
          : colors.textLabel;

    return (
      <View
        style={[
          {
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingHorizontal: 20,
            paddingTop: 6,
            paddingBottom: 14,
          },
          style,
        ]}
        {...rest}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}>
          <NebulaMark size={22} muted={mutedWordmark} />
          <Text
            style={{
              fontSize: 17,
              fontFamily: fonts.uiSemi,
              letterSpacing: -0.255,
              color: mutedWordmark ? '#C8C4DA' : colors.textPrimary,
            }}>
            Nebula
          </Text>
        </View>

        {subtitle ? (
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 7,
              height: 30,
              paddingHorizontal: 12,
              borderRadius: radii.pill,
              backgroundColor: subtitleDanger ? 'rgba(255,92,122,.1)' : 'rgba(139,124,246,.1)',
              borderWidth: 1,
              borderColor: subtitleDanger ? 'rgba(255,92,122,.28)' : 'rgba(139,124,246,.24)',
            }}>
            <View
              style={{
                width: 6,
                height: 6,
                borderRadius: 999,
                backgroundColor: dotColour,
                shadowColor: onlineDot === 'online' ? colors.accentDefault : 'transparent',
                shadowOpacity: onlineDot === 'online' ? 0.9 : 0,
                shadowRadius: 7,
              }}
            />
            <Text
              style={{
                fontSize: 11.5,
                fontFamily: fonts.ui,
                color: subtitleDanger ? colors.dangerOffline : colors.textStudio,
              }}>
              {subtitle}
            </Text>
          </View>
        ) : null}
      </View>
    );
  }

  return (
    <View
      style={[
        {
          paddingHorizontal: 20,
          paddingTop: 2,
          paddingBottom: 14,
          gap: 14,
        },
        style,
      ]}
      {...rest}>
      {title ? (
        <Text
          style={{
            fontSize: 32,
            lineHeight: 34,
            letterSpacing: -1.024,
            fontFamily: fonts.uiBold,
            color: colors.textPrimary,
          }}>
          {title}
        </Text>
      ) : null}
      {children}
    </View>
  );
}
