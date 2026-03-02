'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Inbox, Users, User, Settings, LucideIcon } from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import Image from 'next/image';

interface SidebarLink {
  icon: LucideIcon;
  label: string;
  path: string;
}

interface SidebarSection {
  title: string;
  items: SidebarLink[];
}

const sections: SidebarSection[] = [
  {
    title: 'My Inbox',
    items: [{ icon: Inbox, label: 'My Chats', path: '/agent/inbox' }],
  },
  {
    title: 'My Team',
    items: [{ icon: Users, label: '# Team Channel', path: '/agent/team' }],
  },
];

const footerItems: SidebarLink[] = [
  { icon: User, label: 'Profile', path: '/agent/profile' },
  { icon: Settings, label: 'Settings', path: '/agent/settings' },
];

export function AgentSidebar() {
  const pathname = usePathname();
  const { isCollapsed } = useSidebar();

  const linkClass = (path: string) => {
    const isActive = pathname === path || pathname?.startsWith(path + '/');
    return `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
      isActive ? 'bg-primary text-white' : 'text-text-secondary hover:bg-panel hover:text-text-primary'
    }`;
  };

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
          {sections.map((section) => (
            <div key={section.title} className="mb-4">
              {!isCollapsed && (
                <p className="px-4 mb-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider">
                  {section.title}
                </p>
              )}
              <div className="space-y-0.5">
                {section.items.map((item) => {
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
          ))}

          {!isCollapsed && <div className="border-t border-border my-3" />}
          <div className="space-y-0.5">
            {footerItems.map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.path} href={item.path} className={linkClass(item.path)}>
                  <Icon className="w-5 h-5 flex-shrink-0" />
                  {!isCollapsed && <span className="font-medium text-sm">{item.label}</span>}
                </Link>
              );
            })}
          </div>
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
