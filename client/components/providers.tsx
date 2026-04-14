'use client';

import { AuthSessionProvider } from '@/contexts/AuthSessionContext';
import { TeamsProvider } from '@/contexts/TeamsContext';
import { AgentsProvider } from '@/contexts/AgentsContext';
import { OnlineScheduleProvider } from '@/contexts/OnlineScheduleContext';
import { TenantTimezoneProvider } from '@/contexts/TenantTimezoneContext';
import { SoundAlertsProvider } from '@/contexts/SoundAlertsContext';
import { ToastProvider } from '@/contexts/ToastContext';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthSessionProvider>
      <TenantTimezoneProvider>
        <TeamsProvider>
          <AgentsProvider>
            <OnlineScheduleProvider>
              <SoundAlertsProvider>
                <ToastProvider>{children}</ToastProvider>
              </SoundAlertsProvider>
            </OnlineScheduleProvider>
          </AgentsProvider>
        </TeamsProvider>
      </TenantTimezoneProvider>
    </AuthSessionProvider>
  );
}
