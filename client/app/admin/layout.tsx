'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { AdminSidebar } from '@/components/layout/admin-sidebar';
import { AdminHeader } from '@/components/layout/admin-header';
import { SidebarProvider } from '@/contexts/SidebarContext';
import { useSidebar } from '@/contexts/SidebarContext';
import { API_BASE_URL, clearAuthSession } from '@/lib/auth-session';

const MAIN_SCROLLBAR_HIDDEN = new Set([
  '/admin/agents',
  '/admin/settings',
  '/admin/knowledge-base',
  '/admin/trending-products',
]);

function AdminShell({ children }: { children: React.ReactNode }) {
  const { isCollapsed } = useSidebar();
  const pathname = usePathname();
  const hideMainScrollbar = MAIN_SCROLLBAR_HIDDEN.has(pathname);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(max-width: 767px)');
    const update = () => setIsMobile(mql.matches);
    update();
    mql.addEventListener('change', update);
    return () => mql.removeEventListener('change', update);
  }, []);

  return (
    <div className="flex h-[100svh] overflow-hidden bg-scaffold">
      <AdminSidebar />
      <div
        className="flex min-h-0 flex-1 flex-col overflow-hidden transition-all duration-300"
        style={{ marginLeft: isMobile ? 0 : isCollapsed ? '80px' : '256px' }}
      >
        <AdminHeader />
        <main
          className={`min-h-0 flex-1 overflow-y-auto bg-scaffold p-3 md:p-6${hideMainScrollbar ? ' admin-no-scrollbar' : ''}`}
        >
          {children}
        </main>
      </div>
    </div>
  );
}

function AdminLayoutContent({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        if (typeof window === 'undefined') return;
        const token = localStorage.getItem('auth_token');
        const role = (localStorage.getItem('auth_role') || '').toLowerCase();
        if (!token || role !== 'admin') {
          router.replace('/login');
          return;
        }
        const meRes = await fetch(`${API_BASE_URL}/api/auth/me`, {
          method: 'GET',
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!meRes.ok) {
          clearAuthSession();
          router.replace('/login');
          return;
        }
        const profile = (await meRes.json()) as { role?: string };
        if ((profile.role || '').toLowerCase() !== 'admin') {
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
    void run();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-scaffold">
        <div className="rounded-lg border border-border bg-card px-8 py-10 shadow-sm">
          <div className="h-8 w-40 mx-auto rounded-md bg-border/70 animate-pulse mb-4" />
          <p className="text-xs text-text-muted text-center">Checking session…</p>
        </div>
      </div>
    );
  }

  return <AdminShell>{children}</AdminShell>;
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
