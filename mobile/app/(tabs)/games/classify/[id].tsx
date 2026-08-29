import { useLocalSearchParams } from 'expo-router';

import { ClassifyScreen } from '@/components/games/ClassifyScreen';

export default function ClassifyRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <ClassifyScreen id={id ?? ''} />;
}
