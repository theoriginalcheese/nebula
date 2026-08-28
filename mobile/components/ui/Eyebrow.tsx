import { Text, TextProps } from 'react-native';

import { colors, fonts, typescale } from '@/constants/theme';

type Props = TextProps & {
  children: React.ReactNode;
  color?: string;
  tracking?: 'tight' | 'wide';
};

/** 9.5px/600 uppercase — tracking .16em (stats) or .22em (sections) */
export function Eyebrow({
  children,
  color = colors.textLabel,
  tracking = 'wide',
  style,
  ...rest
}: Props) {
  return (
    <Text
      style={[
        {
          fontSize: typescale.eyebrow.fontSize,
          fontFamily: fonts.uiSemi,
          letterSpacing: tracking === 'wide' ? 2.09 : 1.52,
          textTransform: 'uppercase',
          color,
        },
        style,
      ]}
      {...rest}>
      {children}
    </Text>
  );
}
