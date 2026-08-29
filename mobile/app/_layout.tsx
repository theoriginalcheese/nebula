import {
  JetBrainsMono_500Medium,
  JetBrainsMono_700Bold,
} from '@expo-google-fonts/jetbrains-mono';
import {
  PlusJakartaSans_500Medium,
  PlusJakartaSans_600SemiBold,
  PlusJakartaSans_700Bold,
} from '@expo-google-fonts/plus-jakarta-sans';
import { DarkTheme, ThemeProvider } from '@react-navigation/native';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import 'react-native-reanimated';
import { StatusBar } from 'expo-status-bar';

import { colors } from '@/constants/theme';
import { StudioProvider } from '@/state/StudioContext';

export { ErrorBoundary } from 'expo-router';

/**
 * React Navigation paints its own container behind every screen and defaults to
 * a light one. Without this the ground flashes #F2F2F2 on push/pop.
 */
const navTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: colors.bgScreen,
    card: colors.bgScreen,
    border: colors.tabBarBorder,
    text: colors.textPrimary,
    primary: colors.accentDefault,
  },
};

export const unstable_settings = {
  initialRouteName: '(tabs)',
};

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [loaded, error] = useFonts({
    PlusJakartaSans_500Medium,
    PlusJakartaSans_600SemiBold,
    PlusJakartaSans_700Bold,
    JetBrainsMono_500Medium,
    JetBrainsMono_700Bold,
  });

  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync();
  }, [loaded]);

  if (!loaded) return null;

  return (
    <StudioProvider>
      <ThemeProvider value={navTheme}>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: colors.bgScreen },
          }}>
          <Stack.Screen name="(tabs)" />
          {/*
            Appearance has no entry point anywhere in the eight mockup frames,
            so it stays a reachable-but-unlinked route rather than getting an
            invented gear icon. It also sits outside (tabs), so it renders
            without the tab bar — the mockup shows the bar with nothing
            highlighted, which a 4-tab bar cannot express. Both need a product
            decision.
          */}
          <Stack.Screen name="appearance" options={{ presentation: 'modal' }} />
        </Stack>
      </ThemeProvider>
    </StudioProvider>
  );
}
