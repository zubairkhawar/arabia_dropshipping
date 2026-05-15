'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Inbox, Bell, Users, MessageCircle, type LucideIcon } from 'lucide-react';
import { useAgentPortalRealtime } from '@/contexts/AgentPortalRealtimeContext';
import { useNotifications } from '@/contexts/NotificationsContext';

interface TabItem {
  icon: LucideIcon;
  label: string;
  path: string;
  match: (pathname: string) => boolean;
  unread: number;
}

export function AgentMobileTabBar() {
  const pathname = usePathname() || '';
  const { unread } = useAgentPortalRealtime();
  const { unreadCount: notificationUnread } = useNotifications();

  const items: TabItem[] = [
    {
      icon: Inbox,
      label: 'Inbox',
      path: '/agent/inbox',
      match: (p) => p === '/agent/inbox' || p.startsWith('/agent/inbox/'),
      unread: unread.inbox,
    },
    {
      icon: Users,
      label: 'Team',
      path: '/agent/team',
      match: (p) => p === '/agent/team' || p.startsWith('/agent/team/'),
      unread: unread.team_channel,
    },
    {
      icon: MessageCircle,
      label: 'DM',
      path: '/agent/dm',
      match: (p) => p === '/agent/dm' || p.startsWith('/agent/dm/'),
      unread: 0,
    },
    {
      icon: Bell,
      label: 'Alerts',
      path: '/agent/notifications',
      match: (p) => p === '/agent/notifications' || p.startsWith('/agent/notifications/'),
      unread: notificationUnread,
    },
  ];

  return (
    <nav
      className="xs:hidden fixed bottom-0 left-0 right-0 z-40 flex h-16 items-stretch border-t border-border bg-sidebar pb-[env(safe-area-inset-bottom)]"
      aria-label="Agent navigation"
    >
      {items.map((item) => {
        const Icon = item.icon;
        const active = item.match(pathname);
        return (
          <Link
            key={item.path}
            href={item.path}
            aria-current={active ? 'page' : undefined}
            className={`flex flex-1 flex-col items-center justify-center gap-1 px-1 transition-colors ${
              active ? 'text-primary' : 'text-text-secondary'
            }`}
          >
            <span className="relative inline-flex h-6 w-6 items-center justify-center">
              <Icon className="h-5 w-5" />
              {item.unread > 0 && (
                <span className="absolute -top-1.5 -right-2 flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-red-500 px-0.5 text-[9px] font-semibold leading-none text-white">
                  {item.unread > 99 ? '99+' : item.unread}
                </span>
              )}
            </span>
            <span className="text-[10px] font-medium leading-none">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
