'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Bot,
  Users,
  User,
  TrendingUp,
  FileText,
  Settings,
  LayoutDashboard,
  Inbox,
  LucideIcon,
} from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import Image from 'next/image';

interface SidebarLink {
  icon: LucideIcon;
  label: string;
  path: string;
}

const aiBotSection: SidebarLink[] = [{ icon: Bot, label: 'AI Bot', path: '/admin/inbox' }];

const teamsSection: SidebarLink[] = [
  { icon: Users, label: 'Team A', path: '/admin/teams/team-a' },
  { icon: Users, label: 'Team B', path: '/admin/teams/team-b' },
  { icon: Users, label: 'Team C', path: '/admin/teams/team-c' },
];

const agentsSection: SidebarLink[] = [
  { icon: User, label: 'Ali', path: '/admin/agents/ali' },
  { icon: User, label: 'Hamza', path: '/admin/agents/hamza' },
  { icon: User, label: 'Sarah', path: '/admin/agents/sarah' },
];

const bottomSection: SidebarLink[] = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/admin/dashboard' },
  { icon: TrendingUp, label: 'Analytics', path: '/admin/analytics' },
  { icon: FileText, label: 'System Logs', path: '/admin/logs' },
  { icon: Settings, label: 'Settings', path: '/admin/settings' },
];

export function AdminSidebar() {
  const pathname = usePathname();
  const { isCollapsed } = useSidebar();

  const linkClass = (path: string) => {
    const isActive = pathname === path || pathname?.startsWith(path + '/');
    return `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
      isActive ? 'bg-primary text-white' : 'text-text-secondary hover:bg-panel hover:text-text-primary'
    }`;
  };

  const renderSection = (title: string, items: SidebarLink[]) => (
    <div key={title} className="mb-4">
      {!isCollapsed && (
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
          {renderSection('', aiBotSection)}
          {!isCollapsed && <div className="border-t border-border my-3" />}
          {renderSection('Teams', teamsSection)}
          {renderSection('Agents', agentsSection)}
          {!isCollapsed && <div className="border-t border-border my-3" />}
          {renderSection('', bottomSection)}
        </nav>

        {!isCollapsed && (
          <div className="p-4 border-t border-border">
            <p className="text-xs text-text-muted">© 2024 Arabia Dropshipping</p>
          </div>
        )}
      </div>
    </div>
  );
}
