'use client';

import { TeamsProvider } from '@/contexts/TeamsContext';
import { AgentsProvider } from '@/contexts/AgentsContext';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <TeamsProvider>
      <AgentsProvider>{children}</AgentsProvider>
    </TeamsProvider>
  );
}
