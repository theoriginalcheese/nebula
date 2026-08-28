import { Tabs } from 'expo-router';

import { PillTabBar } from '@/components/PillTabBar';
import { colors } from '@/constants/theme';

export default function TabLayout() {
  return (
    <Tabs
      tabBar={(props) => <PillTabBar {...(props as any)} />}
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.bgScreen },
      } as object}>
      <Tabs.Screen name="index" options={{ title: 'Now' }} />
      <Tabs.Screen name="clips" options={{ title: 'Clips' }} />
      <Tabs.Screen name="remote" options={{ title: 'Remote' }} />
      <Tabs.Screen name="games" options={{ title: 'Games' }} />
    </Tabs>
  );
}
