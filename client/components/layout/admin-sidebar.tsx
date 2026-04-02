'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Users,
  User,
  Settings,
  LayoutDashboard,
  LucideIcon,
  MessageCircle,
  FolderCog,
  ChevronDown,
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
  { icon: MessageCircle, label: 'All Conversations', path: '/admin/inbox' },
  { icon: MessageCircle, label: 'Live Now', path: '/admin/inbox/live' },
  { icon: MessageCircle, label: 'Closed', path: '/admin/inbox/closed' },
];

const bottomSection: SidebarLink[] = [
  { icon: FolderCog, label: 'Knowledge Base', path: '/admin/knowledge-base' },
  { icon: Settings, label: 'Settings', path: '/admin/settings' },
];

export function AdminSidebar() {
  const pathname = usePathname();
  const { isCollapsed } = useSidebar();
  const [conversationsOpen, setConversationsOpen] = useState(true);

  const linkClass = (path: string, exactOnly = false) => {
    const isActive = exactOnly
      ? pathname === path
      : pathname === path || pathname?.startsWith(path + '/');
    return `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
      isActive ? 'bg-primary text-white' : 'text-text-secondary hover:bg-panel hover:text-text-primary'
    }`;
  };

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
            <Link key={item.path} href={item.path} className={linkClass(item.path)}>
              <Icon className="w-5 h-5 flex-shrink-0" />
              {!isCollapsed && <span className="font-medium text-sm">{item.label}</span>}
            </Link>
          );
        })}
      </div>
    </div>
  );

  return (
    <div
      className={`fixed left-0 top-0 h-full bg-sidebar border-r border-border transition-all duration-300 z-50 ${
        isCollapsed ? 'w-20' : 'w-64'
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
                    <Link key={item.path} href={item.path} className={conversationLinkClass(item.path)}>
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
                        <Link key={item.path} href={item.path} className={conversationLinkClass(item.path)}>
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
  );
}
