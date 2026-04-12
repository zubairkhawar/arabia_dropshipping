'use client';

import { usePathname } from 'next/navigation';
import { AdminSidebar } from '@/components/layout/admin-sidebar';
import { AdminHeader } from '@/components/layout/admin-header';
import { SidebarProvider } from '@/contexts/SidebarContext';
import { useSidebar } from '@/contexts/SidebarContext';

const MAIN_SCROLLBAR_HIDDEN = new Set([
  '/admin/agents',
  '/admin/settings',
  '/admin/knowledge-base',
]);

function AdminLayoutContent({ children }: { children: React.ReactNode }) {
  const { isCollapsed } = useSidebar();
  const pathname = usePathname();
  const hideMainScrollbar = MAIN_SCROLLBAR_HIDDEN.has(pathname);

  return (
    <div className="flex h-screen overflow-hidden bg-scaffold">
      <AdminSidebar />
      <div
        className="flex min-h-0 flex-1 flex-col overflow-hidden transition-all duration-300"
        style={{ marginLeft: isCollapsed ? '80px' : '256px' }}
      >
        <AdminHeader />
        <main
          className={`min-h-0 flex-1 overflow-y-auto bg-scaffold p-6${hideMainScrollbar ? ' admin-no-scrollbar' : ''}`}
        >
          {children}
        </main>
      </div>
    </div>
  );
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider>
      <AdminLayoutContent>{children}</AdminLayoutContent>
    </SidebarProvider>
  );
}
