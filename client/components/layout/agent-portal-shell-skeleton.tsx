'use client';

import { useSidebar } from '@/contexts/SidebarContext';
import { AgentSidebar } from '@/components/layout/agent-sidebar';

function HeaderSkeleton() {
  return (
    <header className="h-[64px] border-b border-border bg-white flex items-center justify-between px-4 shrink-0">
      <div className="h-8 w-32 rounded-md bg-border/80 animate-pulse" />
      <div className="flex items-center gap-3">
        <div className="h-9 w-9 rounded-full bg-border/80 animate-pulse" />
        <div className="h-4 w-28 rounded bg-border/80 animate-pulse hidden sm:block" />
      </div>
    </header>
  );
}

function MainSkeleton() {
  return (
    <div className="flex flex-1 min-h-0 overflow-hidden p-4 gap-4">
      <div className="hidden md:flex w-[min(100%,380px)] flex-col gap-3 border-r border-border pr-4">
        <div className="h-9 w-full rounded-lg bg-border/70 animate-pulse" />
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-[72px] rounded-lg bg-border/50 animate-pulse" style={{ animationDelay: `${i * 80}ms` }} />
        ))}
      </div>
      <div className="flex-1 flex flex-col gap-4 min-w-0">
        <div className="h-10 w-48 rounded-md bg-border/70 animate-pulse" />
        <div className="flex-1 rounded-xl bg-border/40 animate-pulse min-h-[200px]" />
      </div>
    </div>
  );
}

export function AgentPortalShellSkeleton() {
  const { isCollapsed } = useSidebar();
  return (
    <div className="flex h-screen bg-scaffold">
      <AgentSidebar />
      <div
        className="flex-1 flex flex-col transition-all duration-300"
        style={{ marginLeft: isCollapsed ? '80px' : '256px' }}
      >
        <HeaderSkeleton />
        <main className="flex-1 overflow-hidden bg-scaffold">
          <MainSkeleton />
        </main>
      </div>
    </div>
  );
}
