'use client';

import { AgentSidebar } from '@/components/layout/agent-sidebar';
import { AgentHeader } from '@/components/layout/agent-header';
import { AgentPortalShellSkeleton } from '@/components/layout/agent-portal-shell-skeleton';
import { SidebarProvider } from '@/contexts/SidebarContext';
import { AgentProfileProvider } from '@/contexts/AgentProfileContext';
import { AgentPresenceProvider } from '@/contexts/AgentPresenceContext';
import { DmChatsProvider } from '@/contexts/DmChatsContext';
import { NotificationsProvider } from '@/contexts/NotificationsContext';
import { useSidebar } from '@/contexts/SidebarContext';
import { clearAuthAgentId } from '@/lib/agent-session-storage';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

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
          fetch(`${API_BASE}/api/auth/me`, { method: 'GET', headers: authHeaders }),
          fetch(`${API_BASE}/api/agents/me`, { method: 'GET', headers: authHeaders }),
        ]);
        if (!meRes.ok) {
          localStorage.removeItem('auth_token');
          localStorage.removeItem('auth_token_type');
          localStorage.removeItem('auth_email');
          localStorage.removeItem('auth_role');
          clearAuthAgentId();
          router.replace('/login');
          return;
        }

        const profile = (await meRes.json()) as { role?: string };
        if ((profile.role || '').toLowerCase() !== 'agent') {
          router.replace('/login');
          return;
        }

        if (!agentMeRes.ok) {
          localStorage.removeItem('auth_token');
          localStorage.removeItem('auth_token_type');
          localStorage.removeItem('auth_email');
          localStorage.removeItem('auth_role');
          clearAuthAgentId();
          router.replace('/login');
          return;
        }
        if (!cancelled) setAuthChecked(true);
      } catch {
        clearAuthAgentId();
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
        <main className="flex-1 overflow-hidden bg-scaffold">{children}</main>
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
          <NotificationsProvider>
            <DmChatsProvider>
              <AgentLayoutContent>{children}</AgentLayoutContent>
            </DmChatsProvider>
          </NotificationsProvider>
        </AgentPresenceProvider>
      </AgentProfileProvider>
    </SidebarProvider>
  );
}
