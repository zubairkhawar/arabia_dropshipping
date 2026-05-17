'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Users,
  User,
  Settings,
  LayoutDashboard,
  LucideIcon,
  MessageCircle,
  Radio,
  CheckCircle2,
  FolderCog,
  ChevronDown,
  ShoppingBag,
  Megaphone,
} from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import Image from 'next/image';

interface SidebarLink {
  icon: LucideIcon;
  label: string;
  path: string;
}

const dashboardSection: SidebarLink[] = [{ icon: LayoutDashboard, label: 'Dashboard', path: '/admin/dashboard' }];

const teamsSection: SidebarLink[] = [{ icon: Users, label: 'Teams', path: '/admin/teams' }];

const agentsSection: SidebarLink[] = [{ icon: User, label: 'Agents', path: '/admin/agents' }];

const conversationsViews: SidebarLink[] = [
  { icon: Radio, label: 'Live Now', path: '/admin/inbox/live' },
  { icon: CheckCircle2, label: 'Closed', path: '/admin/inbox/closed' },
];

const bottomSection: SidebarLink[] = [
  { icon: FolderCog, label: 'Knowledge Base', path: '/admin/knowledge-base' },
  { icon: ShoppingBag, label: 'Products', path: '/admin/trending-products' },
  { icon: Megaphone, label: 'Broadcasts', path: '/admin/broadcasts' },
  { icon: Settings, label: 'Settings', path: '/admin/settings' },
];

export function AdminSidebar() {
  const pathname = usePathname();
  const { isCollapsed: rawCollapsed, mobileOpen, closeMobileSidebar } = useSidebar();
  const [conversationsOpen, setConversationsOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(max-width: 767px)');
    const update = () => setIsMobile(mql.matches);
    update();
    mql.addEventListener('change', update);
    return () => mql.removeEventListener('change', update);
  }, []);

  // On mobile the sidebar is a drawer at full width; the desktop collapse flag must not apply.
  const isCollapsed = !isMobile && rawCollapsed;

  const linkClass = (path: string, exactOnly = false) => {
    const isActive = exactOnly
      ? pathname === path
      : pathname === path || pathname?.startsWith(path + '/');
    return `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
      isActive ? 'bg-primary text-white' : 'text-text-secondary hover:bg-panel hover:text-text-primary'
    }`;
  };

  const handleNav = () => closeMobileSidebar();

  /** Conversation views are siblings; only one should be active (exact path match). */
  const conversationLinkClass = (path: string) => linkClass(path, true);

  const renderSection = (title: string, items: SidebarLink[]) => (
    <div key={title} className="mb-4">
      {!isCollapsed && title && (
        <p className="px-4 mb-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider">{title}</p>
      )}
      <div className="space-y-0.5">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <Link key={item.path} href={item.path} onClick={handleNav} className={linkClass(item.path)}>
              <Icon className="w-5 h-5 flex-shrink-0" />
              {!isCollapsed && <span className="font-medium text-sm">{item.label}</span>}
            </Link>
          );
        })}
      </div>
    </div>
  );

  return (
    <>
    {/* Mobile scrim */}
    <div
      className={`md:hidden fixed inset-0 z-40 bg-black/40 transition-opacity duration-200 ${
        mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
      }`}
      onClick={closeMobileSidebar}
      aria-hidden
    />
    <div
      className={`fixed left-0 top-0 h-full bg-sidebar border-r border-border transition-all duration-300 z-50 max-md:w-72 max-md:transform max-md:transition-transform ${
        mobileOpen ? 'max-md:translate-x-0' : 'max-md:-translate-x-full'
      } ${
        isCollapsed ? 'md:w-20' : 'md:w-64'
      }`}
    >
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between p-4 border-b border-border">
          {isCollapsed ? (
            <div className="flex items-center justify-center w-full">
              <Image src="/Arabia_thumbnail.png" alt="Arabia" width={32} height={32} className="h-8 w-8" />
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Image src="/Arabia_thumbnail.png" alt="Arabia" width={32} height={32} className="h-8 w-8" />
              <Image src="/arabia_logo.png" alt="Arabia Dropshipping" width={120} height={32} className="h-8 w-auto" />
            </div>
          )}
        </div>

        <nav className="flex-1 p-3 overflow-y-auto">
          {renderSection('Dashboard', dashboardSection)}
          {!isCollapsed && <div className="border-t border-border my-3" />}
          {renderSection('Teams', teamsSection)}
          {renderSection('Agents', agentsSection)}

          {/* Conversations dropdown behaves like Slack/Notion section */}
          <div className="mb-4">
            {!isCollapsed && (
              <p className="px-4 mb-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider">
                Conversations
              </p>
            )}
            {isCollapsed ? (
              <div className="space-y-0.5">
                {conversationsViews.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link key={item.path} href={item.path} onClick={handleNav} className={conversationLinkClass(item.path)}>
                      <Icon className="w-5 h-5 flex-shrink-0" />
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="space-y-0.5">
                <button
                  type="button"
                  onClick={() => setConversationsOpen((open) => !open)}
                  className="w-full flex items-center justify-between px-4 py-2.5 rounded-lg text-sm font-medium text-text-secondary hover:bg-panel hover:text-text-primary transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <MessageCircle className="w-5 h-5 flex-shrink-0" />
                    <span>Conversations</span>
                  </span>
                  <ChevronDown
                    className={`w-4 h-4 text-text-muted transition-transform ${
                      conversationsOpen ? 'rotate-180' : ''
                    }`}
                  />
                </button>
                {conversationsOpen && (
                  <div className="pl-4 space-y-0.5">
                    {conversationsViews.map((item) => {
                      const Icon = item.icon;
                      return (
                        <Link key={item.path} href={item.path} onClick={handleNav} className={conversationLinkClass(item.path)}>
                          <Icon className="w-4 h-4 flex-shrink-0" />
                          <span className="font-medium text-sm">{item.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>

          {!isCollapsed && <div className="border-t border-border my-3" />}
          {renderSection('', bottomSection)}
        </nav>

        {!isCollapsed && (
          <div className="p-4 border-t border-border">
            <p className="text-xs text-text-muted">© 2026 Arabia Dropshipping</p>
          </div>
        )}
      </div>
    </div>
    </>
  );
}
