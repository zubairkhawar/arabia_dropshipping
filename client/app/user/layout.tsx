'use client';

import { UserSidebar } from '@/components/layout/user-sidebar';
import { UserHeader } from '@/components/layout/user-header';
import { SidebarProvider } from '@/contexts/SidebarContext';
import { useSidebar } from '@/contexts/SidebarContext';

function UserLayoutContent({ children }: { children: React.ReactNode }) {
  const { isCollapsed } = useSidebar();

  return (
    <div className="flex h-screen bg-scaffold">
      <UserSidebar />
      <div
        className="flex-1 flex flex-col transition-all duration-300"
        style={{ marginLeft: isCollapsed ? '80px' : '256px' }}
      >
        <UserHeader />
        <main className="flex-1 overflow-y-auto p-6 bg-scaffold">{children}</main>
      </div>
    </div>
  );
}

export default function UserLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider>
      <UserLayoutContent>{children}</UserLayoutContent>
    </SidebarProvider>
  );
}
