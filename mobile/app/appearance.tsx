import { StyleSheet, Text, View } from 'react-native';

import { colours, fonts } from '@/constants/theme';

/**
 * Appearance settings stub.
 * DESIGN GAP: BUILD-SPEC / FRAMES note no shown entry point among the 4 tabs.
 * Route exists for deep-link / later design decision — do not invent a gear icon.
 */
export default function AppearanceScreen() {
  return (
    <View style={styles.screen}>
      <Text style={styles.title}>Appearance</Text>
      <Text style={styles.body}>
        Stub only. Accent presets + motion slider land after design names an
        entry point. No fake sliders.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colours.bgScreen,
    padding: 20,
  },
  title: {
    fontFamily: fonts.uiBold,
    fontSize: 32,
    color: colours.textPrimary,
    marginBottom: 8,
  },
  body: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colours.textMuted,
  },
});
