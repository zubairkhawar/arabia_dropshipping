'use client';

import { useState } from 'react';
import { Search, Bell, User, ChevronDown, LogOut, Settings, Menu, PanelLeftClose } from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import Image from 'next/image';

interface TopBarBaseProps {
  userRole?: string;
  userName?: string;
}

export function TopBarBase({ userRole = 'User', userName = 'Store Owner' }: TopBarBaseProps) {
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const { isCollapsed, toggleSidebar } = useSidebar();

  const notifications = [
    { id: 1, message: 'New order #1234 received', time: '2 min ago' },
    { id: 2, message: 'Order #1230 delivered successfully', time: '1 hour ago' },
    { id: 3, message: 'New conversation assigned', time: '3 hours ago' },
  ];

  return (
    <div 
      className="h-16 bg-bar border-b border-border flex items-center justify-between px-6 transition-all duration-300"
      style={{ marginLeft: isCollapsed ? '80px' : '256px' }}
    >
      {/* Left side: sidebar toggle + search */}
      <div className="flex items-center gap-4 flex-1">
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-lg border border-border bg-white hover:bg-panel transition-colors"
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? (
            <Menu className="w-5 h-5 text-text-secondary" />
          ) : (
            <PanelLeftClose className="w-5 h-5 text-text-secondary" />
          )}
        </button>

        <div className="flex-1 max-w-md">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-text-muted" />
            <input
              type="text"
              placeholder="Search orders, products, customers..."
              className="w-full pl-10 pr-4 py-2 bg-panel border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-primary focus:bg-white"
            />
          </div>
        </div>
      </div>

      {/* Right Side */}
      <div className="flex items-center gap-4">
        {/* Notifications */}
        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-lg hover:bg-panel transition-colors"
          >
            <Bell className="w-5 h-5 text-text-primary" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-primary rounded-full"></span>
          </button>

          {showNotifications && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowNotifications(false)}
              ></div>
              <div className="absolute right-0 mt-2 w-80 bg-white border border-border rounded-lg shadow-xl z-20">
                <div className="p-4 border-b border-border">
                  <h3 className="font-semibold text-text-primary">Notifications</h3>
                </div>
                <div className="max-h-96 overflow-y-auto">
                  {notifications.map((notif) => (
                    <div
                      key={notif.id}
                      className="p-4 border-b border-border hover:bg-panel cursor-pointer"
                    >
                      <p className="text-sm text-text-primary">{notif.message}</p>
                      <p className="text-xs text-text-muted mt-1">{notif.time}</p>
                    </div>
                  ))}
                </div>
                <div className="p-4 border-t border-border">
                  <button className="text-sm text-primary hover:text-primary-dark">
                    View all notifications
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* User Menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-panel transition-colors"
          >
            <div className="w-8 h-8 bg-primary rounded-full flex items-center justify-center">
              <User className="w-5 h-5 text-white" />
            </div>
            <span className="text-text-primary font-medium">{userName}</span>
            <ChevronDown className="w-4 h-4 text-text-muted" />
          </button>

          {showUserMenu && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowUserMenu(false)}
              ></div>
              <div className="absolute right-0 mt-2 w-48 bg-white border border-border rounded-lg shadow-xl z-20">
                <div className="p-2">
                  <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2">
                    <User className="w-4 h-4" />
                    Profile
                  </button>
                  <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2">
                    <Settings className="w-4 h-4" />
                    Settings
                  </button>
                  <div className="border-t border-border my-2"></div>
                  <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-status-error flex items-center gap-2">
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
