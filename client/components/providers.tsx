'use client';

import { TeamsProvider } from '@/contexts/TeamsContext';
import { AgentsProvider } from '@/contexts/AgentsContext';
import { OnlineScheduleProvider } from '@/contexts/OnlineScheduleContext';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <TeamsProvider>
      <AgentsProvider>
        <OnlineScheduleProvider>{children}</OnlineScheduleProvider>
      </AgentsProvider>
    </TeamsProvider>
  );
}
