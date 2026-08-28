import { BlurView } from 'expo-blur';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Ellipse, Path, Rect } from 'react-native-svg';

import { colors, fonts } from '@/constants/theme';

type TabKey = 'index' | 'clips' | 'remote' | 'games';

function TabIcon({ name, active }: { name: TabKey; active: boolean }) {
  const c = active ? colors.textAccentSoft : colors.textLabel;
  switch (name) {
    case 'index':
      return (
        <Svg width={21} height={21} viewBox="0 0 24 24" fill="none">
          <Circle cx="12" cy="12" r="3.2" stroke={c} strokeWidth={1.5} />
          <Ellipse
            cx="12"
            cy="12"
            rx="9.6"
            ry="4.6"
            stroke={c}
            strokeWidth={1.5}
            transform="rotate(-22 12 12)"
          />
        </Svg>
      );
    case 'clips':
      return (
        <Svg width={21} height={21} viewBox="0 0 24 24" fill="none">
          <Rect x="3" y="5.5" width="18" height="13" rx="2.6" stroke={c} strokeWidth={1.5} />
          <Path d="M10 9.6v4.8l4.2-2.4z" fill={c} />
        </Svg>
      );
    case 'remote':
      return (
        <Svg width={21} height={21} viewBox="0 0 24 24" fill="none">
          <Path
            d="M4.6 9.4a10.5 10.5 0 0 1 14.8 0M7.7 12.8a6.2 6.2 0 0 1 8.6 0"
            stroke={c}
            strokeWidth={1.5}
            strokeLinecap="round"
          />
          <Circle cx="12" cy="16.6" r="1.5" fill={c} />
        </Svg>
      );
    case 'games':
      return (
        <Svg width={21} height={21} viewBox="0 0 24 24" fill="none">
          <Rect x="3" y="6.5" width="18" height="11" rx="3.4" stroke={c} strokeWidth={1.5} />
          <Path
            d="M7.4 10.4v3.2M5.8 12h3.2M15.6 11.4h.01M17.8 13.2h.01"
            stroke={c}
            strokeWidth={1.5}
            strokeLinecap="round"
          />
        </Svg>
      );
  }
}

const LABELS: Record<TabKey, string> = {
  index: 'Now',
  clips: 'Clips',
  remote: 'Remote',
  games: 'Games',
};

type TabBarProps = {
  state: { index: number; routes: Array<{ key: string; name: string }> };
  navigation: {
    emit: (e: { type: string; target: string; canPreventDefault: boolean }) => {
      defaultPrevented: boolean;
    };
    navigate: (name: string) => void;
  };
};

export function PillTabBar({ state, navigation }: TabBarProps) {
  const insets = useSafeAreaInsets();
  // Design: margin 0 14px 26px — keep 26 above home indicator when possible
  const bottom = Math.max(insets.bottom, 0) + (insets.bottom > 0 ? 8 : 26);

  return (
    <View pointerEvents="box-none" style={[styles.wrap, { bottom }]}>
      <View style={styles.shadowHost}>
        <BlurView intensity={Platform.OS === 'web' ? 40 : 70} tint="dark" style={styles.blur}>
          <View style={styles.inner}>
            {state.routes.map((route, index) => {
              const name = route.name as TabKey;
              if (!LABELS[name]) return null;
              const focused = state.index === index;
              return (
                <Pressable
                  key={route.key}
                  accessibilityRole="button"
                  accessibilityState={focused ? { selected: true } : {}}
                  onPress={() => {
                    const event = navigation.emit({
                      type: 'tabPress',
                      target: route.key,
                      canPreventDefault: true,
                    });
                    if (!focused && !event.defaultPrevented) navigation.navigate(route.name);
                  }}
                  style={styles.item}>
                  <TabIcon name={name} active={focused} />
                  <Text
                    style={{
                      fontSize: 9.5,
                      letterSpacing: 0.19,
                      fontFamily: focused ? fonts.uiSemi : fonts.ui,
                      color: focused ? colors.textAccentSoft : colors.textLabel,
                    }}>
                    {LABELS[name]}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </BlurView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 14,
    right: 14,
  },
  shadowHost: {
    height: 64,
    borderRadius: 26,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: colors.tabBarBorder,
    backgroundColor: colors.tabBarBg,
    ...Platform.select({
      web: {
        boxShadow: '0 12px 34px rgba(0,0,0,0.5)',
      },
      default: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 12 },
        shadowOpacity: 0.5,
        shadowRadius: 34,
        elevation: 16,
      },
    }),
  },
  blur: { flex: 1 },
  inner: { flex: 1, flexDirection: 'row' },
  item: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
});
