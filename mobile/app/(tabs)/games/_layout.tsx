import { Stack } from 'expo-router';

import { colors } from '@/constants/theme';

/**
 * Games tab owns its own stack so Classify can be pushed from Games while the
 * single PillTabBar stays mounted in (tabs)/_layout with Games still active —
 * FRAMES: "Classify has no tab of its own".
 */
export default function GamesStackLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.bgScreen },
      }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="classify/[id]" />
    </Stack>
  );
}
