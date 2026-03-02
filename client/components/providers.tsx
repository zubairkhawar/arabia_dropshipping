'use client';

import { TeamsProvider } from '@/contexts/TeamsContext';

export function Providers({ children }: { children: React.ReactNode }) {
  return <TeamsProvider>{children}</TeamsProvider>;
}
