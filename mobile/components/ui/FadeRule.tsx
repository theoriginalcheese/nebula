import { LinearGradient } from 'expo-linear-gradient';

/**
 * Hairline rule with masked-fade ends —
 * `linear-gradient(90deg,transparent,rgba(245,243,255,.11) 20%,… 80%,transparent)`.
 */
export function FadeRule({ opacity = 0.11 }: { opacity?: number }) {
  const ink = `rgba(245,243,255,${opacity})`;
  return (
    <LinearGradient
      colors={['transparent', ink, ink, 'transparent']}
      locations={[0, 0.2, 0.8, 1]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 0 }}
      style={{ height: 1, width: '100%' }}
    />
  );
}
