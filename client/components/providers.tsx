'use client';

import { TeamsProvider } from '@/contexts/TeamsContext';
import { AgentsProvider } from '@/contexts/AgentsContext';
import { OnlineScheduleProvider } from '@/contexts/OnlineScheduleContext';
import { ToastProvider } from '@/contexts/ToastContext';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <TeamsProvider>
      <AgentsProvider>
        <OnlineScheduleProvider>
          <ToastProvider>{children}</ToastProvider>
        </OnlineScheduleProvider>
      </AgentsProvider>
    </TeamsProvider>
  );
}
