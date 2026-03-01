'use client';

import { AgentSidebar } from '@/components/layout/agent-sidebar';
import { AgentHeader } from '@/components/layout/agent-header';
import { SidebarProvider } from '@/contexts/SidebarContext';
import { useSidebar } from '@/contexts/SidebarContext';

function AgentLayoutContent({ children }: { children: React.ReactNode }) {
  const { isCollapsed } = useSidebar();

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
      <AgentLayoutContent>{children}</AgentLayoutContent>
    </SidebarProvider>
  );
}
