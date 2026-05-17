'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, User, ChevronDown, LogOut, Settings, PanelRightOpen, PanelLeftClose, Menu } from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';

interface TopBarBaseProps {
  userRole?: string;
  userName?: string;
}

export function TopBarBase({ userRole = 'User', userName = 'Store Owner' }: TopBarBaseProps) {
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const { isCollapsed, toggleSidebar, openMobileSidebar } = useSidebar();
  const router = useRouter();

  return (
    <>
    <div className="bg-bar pt-[env(safe-area-inset-top)] md:pt-0">
    <div
      className="h-16 bg-bar border-b border-border flex items-center justify-between px-3 md:px-6 transition-all duration-300 w-full gap-2"
    >
      {/* Left side: sidebar toggle + search */}
      <div className="flex items-center gap-2 md:gap-4 flex-1 min-w-0">
        {/* Mobile hamburger opens the sidebar drawer */}
        <button
          onClick={openMobileSidebar}
          className="md:hidden p-2 rounded-lg border border-border bg-white hover:bg-panel transition-colors"
          aria-label="Open menu"
        >
          <Menu className="w-5 h-5 text-text-secondary" />
        </button>
        {/* Desktop sidebar collapse/expand */}
        <button
          onClick={toggleSidebar}
          className="hidden md:inline-flex p-2 rounded-lg border border-border bg-white hover:bg-panel transition-colors"
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? (
            <PanelRightOpen className="w-5 h-5 text-text-secondary" />
          ) : (
            <PanelLeftClose className="w-5 h-5 text-text-secondary" />
          )}
        </button>

        {/* Mobile search toggle */}
        <button
          type="button"
          onClick={() => setMobileSearchOpen((v) => !v)}
          className="md:hidden p-2 rounded-lg border border-border bg-white hover:bg-panel transition-colors"
          aria-label="Toggle search"
        >
          <Search className="w-5 h-5 text-text-secondary" />
        </button>

        <div className="hidden md:block flex-1 max-w-md">
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
      <div className="flex items-center gap-1.5 md:gap-4 shrink-0">
        {/* User Menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-2 md:px-3 py-2 rounded-lg hover:bg-panel transition-colors"
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
            <span className="hidden md:inline text-text-primary font-medium">{userName}</span>
            <ChevronDown className="hidden md:inline w-4 h-4 text-text-muted" />
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
                  <button
                    type="button"
                    onClick={() => {
                      setShowUserMenu(false);
                      if (typeof window !== 'undefined') {
                        localStorage.clear();
                        sessionStorage.clear();
                      }
                      router.push('/login');
                    }}
                    className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-status-error flex items-center gap-2"
                  >
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
    </div>
    {mobileSearchOpen && (
      <div className="md:hidden border-b border-border bg-bar px-3 py-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" />
          <input
            type="text"
            placeholder="Search orders, products, customers..."
            className="w-full pl-10 pr-4 py-2 bg-panel border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-primary focus:bg-white text-sm"
            autoFocus
          />
        </div>
      </div>
    )}
    </>
  );
}
