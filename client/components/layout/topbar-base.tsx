'use client';

import { useState } from 'react';
import { Search, User, ChevronDown, LogOut, Settings, PanelRightOpen, PanelLeftClose } from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import Image from 'next/image';

interface TopBarBaseProps {
  userRole?: string;
  userName?: string;
}

export function TopBarBase({ userRole = 'User', userName = 'Store Owner' }: TopBarBaseProps) {
  const [showUserMenu, setShowUserMenu] = useState(false);
  const { isCollapsed, toggleSidebar } = useSidebar();

  return (
    <div 
      className="h-16 bg-bar border-b border-border flex items-center justify-between px-6 transition-all duration-300 w-full"
    >
      {/* Left side: sidebar toggle + search */}
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
        {/* User Menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-panel transition-colors"
          >
            {userRole === 'admin' ? (
              <div className="w-8 h-8 rounded-full flex items-center justify-center border border-border bg-white">
                <User className="w-5 h-5 text-black" />
              </div>
            ) : (
              <div className="w-8 h-8 bg-primary rounded-full flex items-center justify-center">
                <User className="w-5 h-5 text-white" />
              </div>
            )}
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
                  {userRole !== 'admin' && (
                    <>
                      <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2">
                        <User className="w-4 h-4" />
                        Profile
                      </button>
                      <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2">
                        <Settings className="w-4 h-4" />
                        Settings
                      </button>
                      <div className="border-t border-border my-2"></div>
                    </>
                  )}
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
