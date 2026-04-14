'use client';

import { AgentSidebar } from '@/components/layout/agent-sidebar';
import { AgentHeader } from '@/components/layout/agent-header';
import { AgentPortalShellSkeleton } from '@/components/layout/agent-portal-shell-skeleton';
import { SidebarProvider } from '@/contexts/SidebarContext';
import { AgentProfileProvider } from '@/contexts/AgentProfileContext';
import { AgentPresenceProvider } from '@/contexts/AgentPresenceContext';
import { DmChatsProvider } from '@/contexts/DmChatsContext';
import { AgentPortalRealtimeProvider } from '@/contexts/AgentPortalRealtimeContext';
import { SoundAlertsBridge } from '@/components/agent/SoundAlertsBridge';
import { NotificationsProvider } from '@/contexts/NotificationsContext';
import { AgentSearchProvider } from '@/contexts/AgentSearchContext';
import { useSidebar } from '@/contexts/SidebarContext';
import { clearAuthSession, API_BASE_URL } from '@/lib/auth-session';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

function AgentLayoutContent({ children }: { children: React.ReactNode }) {
  const { isCollapsed } = useSidebar();
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const validate = async () => {
      try {
        if (typeof window === 'undefined') return;
        const token = localStorage.getItem('auth_token');
        const role = (localStorage.getItem('auth_role') || '').toLowerCase();
        if (!token || role !== 'agent') {
          router.replace('/login');
          return;
        }

        const authHeaders = { Authorization: `Bearer ${token}` };
        const [meRes, agentMeRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/auth/me`, { method: 'GET', headers: authHeaders }),
          fetch(`${API_BASE_URL}/api/agents/me`, { method: 'GET', headers: authHeaders }),
        ]);
        if (!meRes.ok) {
          clearAuthSession();
          router.replace('/login');
          return;
        }

        const profile = (await meRes.json()) as { role?: string };
        if ((profile.role || '').toLowerCase() !== 'agent') {
          router.replace('/login');
          return;
        }

        if (!agentMeRes.ok) {
          clearAuthSession();
          router.replace('/login');
          return;
        }
        if (!cancelled) setAuthChecked(true);
      } catch {
        clearAuthSession();
        router.replace('/login');
      }
    };
    void validate();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!authChecked) {
    return <AgentPortalShellSkeleton />;
  }

  return (
    <div className="flex h-screen bg-scaffold">
      <AgentSidebar />
      <div
        className="flex-1 flex flex-col transition-all duration-300"
        style={{ marginLeft: isCollapsed ? '80px' : '256px' }}
      >
        <AgentHeader />
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-scaffold">{children}</main>
      </div>
    </div>
  );
}

export default function AgentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider>
      <AgentProfileProvider>
        <AgentPresenceProvider>
          <AgentPortalRealtimeProvider>
            <NotificationsProvider>
              <SoundAlertsBridge />
              <AgentSearchProvider>
                <DmChatsProvider>
                  <AgentLayoutContent>{children}</AgentLayoutContent>
                </DmChatsProvider>
              </AgentSearchProvider>
            </NotificationsProvider>
          </AgentPortalRealtimeProvider>
        </AgentPresenceProvider>
      </AgentProfileProvider>
    </SidebarProvider>
  );
}
