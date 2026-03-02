'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Search, Bell, User, ChevronDown, LogOut, Settings, PanelRightOpen, PanelLeftClose, MessageSquarePlus } from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import { useAgentProfile } from '@/contexts/AgentProfileContext';
import { usePathname } from 'next/navigation';

type AgentStatus = 'online' | 'busy' | 'offline';

const statusConfig: Record<AgentStatus, { label: string; dotClass: string }> = {
  online: { label: 'Online', dotClass: 'bg-status-success' },
  busy: { label: 'Busy', dotClass: 'bg-status-warning' },
  offline: { label: 'Offline', dotClass: 'bg-text-muted' },
};

interface AgentHeaderProps {
  userName?: string;
}

export function AgentHeader({ userName }: AgentHeaderProps) {
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showStatusMenu, setShowStatusMenu] = useState(false);
  const [agentStatus, setAgentStatus] = useState<AgentStatus>('online');
  const { isCollapsed, toggleSidebar } = useSidebar();
  const { avatarUrl, fullName } = useAgentProfile();
  const pathname = usePathname();
  const displayName = fullName || userName || 'Support Agent';
  const isInternalDmArea = pathname?.startsWith('/agent/dm') || pathname?.startsWith('/agent/team');

  const notifications = [
    { id: 1, message: 'New conversation assigned', time: '2 min ago' },
    { id: 2, message: 'Customer requested callback', time: '1 hour ago' },
  ];

  return (
    <div className="h-16 bg-bar border-b border-border flex items-center justify-between px-6 transition-all duration-300 w-full">
      <div className="flex items-center gap-4 flex-1">
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-lg border border-border bg-white hover:bg-panel transition-colors"
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? (
            <PanelRightOpen className="w-5 h-5 text-text-secondary" />
          ) : (
            <PanelLeftClose className="w-5 h-5 text-text-secondary" />
          )}
        </button>
        <div className="flex-1 max-w-md">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" />
              <input
                type="text"
                placeholder="Search my chats..."
                className="w-full pl-10 pr-4 py-2 bg-panel border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-primary focus:bg-white text-sm"
              />
            </div>
            {isInternalDmArea && (
              <button
                type="button"
                className="p-2 rounded-lg border border-border bg-white hover:bg-panel transition-colors"
                aria-label="New direct message"
              >
                <MessageSquarePlus className="w-5 h-5 text-text-secondary" />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative">
          <button
            onClick={() => setShowStatusMenu(!showStatusMenu)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-white hover:bg-panel transition-colors"
          >
            <span className={`w-2.5 h-2.5 rounded-full ${statusConfig[agentStatus].dotClass}`} />
            <span className="text-sm font-medium text-text-primary">{statusConfig[agentStatus].label}</span>
            <ChevronDown className="w-4 h-4 text-text-muted" />
          </button>
          {showStatusMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowStatusMenu(false)} />
              <div className="absolute right-0 mt-1 w-40 bg-white border border-border rounded-lg shadow-xl z-20 py-1">
                {(Object.keys(statusConfig) as AgentStatus[]).map((status) => (
                  <button
                    key={status}
                    onClick={() => {
                      setAgentStatus(status);
                      setShowStatusMenu(false);
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-panel text-sm"
                  >
                    <span className={`w-2 h-2 rounded-full ${statusConfig[status].dotClass}`} />
                    {statusConfig[status].label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-lg hover:bg-panel transition-colors"
          >
            <Bell className="w-5 h-5 text-text-primary" />
            {notifications.length > 0 && (
              <span className="absolute top-1 right-1 w-2 h-2 bg-primary rounded-full" />
            )}
          </button>
          {showNotifications && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowNotifications(false)} />
              <div className="absolute right-0 mt-2 w-80 bg-white border border-border rounded-lg shadow-xl z-20">
                <div className="p-4 border-b border-border">
                  <h3 className="font-semibold text-text-primary">Notifications</h3>
                </div>
                <div className="max-h-96 overflow-y-auto">
                  {notifications.map((n) => (
                    <div key={n.id} className="p-4 border-b border-border hover:bg-panel cursor-pointer">
                      <p className="text-sm text-text-primary">{n.message}</p>
                      <p className="text-xs text-text-muted mt-1">{n.time}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-panel transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden flex-shrink-0">
              {avatarUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
              ) : (
                <User className="w-5 h-5 text-primary" />
              )}
            </div>
            <span className="text-text-primary font-medium text-sm">{displayName}</span>
            <ChevronDown className="w-4 h-4 text-text-muted" />
          </button>
          {showUserMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowUserMenu(false)} />
              <div className="absolute right-0 mt-2 w-48 bg-white border border-border rounded-lg shadow-xl z-20">
                <div className="p-2">
                  <Link
                    href="/agent/profile"
                    className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2 text-sm block"
                    onClick={() => setShowUserMenu(false)}
                  >
                    <User className="w-4 h-4" />
                    Profile
                  </Link>
                  <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2 text-sm">
                    <Settings className="w-4 h-4" />
                    Settings
                  </button>
                  <div className="border-t border-border my-2" />
                  <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-status-error flex items-center gap-2 text-sm">
                    <LogOut className="w-4 h-4" />
                    Logout
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
