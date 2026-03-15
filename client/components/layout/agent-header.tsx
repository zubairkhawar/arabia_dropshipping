'use client';

import { useState, useRef, useEffect } from 'react';
import { Search, Bell, User, ChevronDown, LogOut, Settings, PanelRightOpen, PanelLeftClose, Camera, ImagePlus, Trash2, X, Copy } from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import { useAgentProfile } from '@/contexts/AgentProfileContext';
import { useAgents } from '@/contexts/AgentsContext';
import { usePathname } from 'next/navigation';

type AgentStatus = 'active' | 'offline';

const statusConfig: Record<AgentStatus, { label: string; dotClass: string }> = {
  active: { label: 'Active', dotClass: 'bg-status-success' },
  offline: { label: 'Offline', dotClass: 'bg-text-muted' },
};

interface AgentHeaderProps {
  userName?: string;
}

export function AgentHeader({ userName }: AgentHeaderProps) {
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showStatusMenu, setShowStatusMenu] = useState(false);
  const [showProfilePopup, setShowProfilePopup] = useState(false);
  const [showAvatarMenu, setShowAvatarMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const avatarMenuRef = useRef<HTMLDivElement>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus>('active');
  const { isCollapsed, toggleSidebar } = useSidebar();
  const { avatarUrl, fullName, setAvatarUrl, setFullName } = useAgentProfile();
  const { currentAgentId, updateAgent, getCurrentAgent } = useAgents();
  const currentAgent = getCurrentAgent();
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordMessage, setPasswordMessage] = useState<'success' | 'error' | null>(null);
  const pathname = usePathname();
  const displayName = fullName || userName || 'Support Agent';

  const notifications = [
    { id: 1, message: 'New conversation assigned', time: '2 min ago' },
    { id: 2, message: 'Customer requested callback', time: '1 hour ago' },
  ];

  useEffect(() => {
    if (!showAvatarMenu) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        avatarMenuRef.current &&
        !avatarMenuRef.current.contains(e.target as Node) &&
        !(e.target as HTMLElement).closest('button[data-avatar-trigger]')
      ) {
        setShowAvatarMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showAvatarMenu]);

  const handleChoosePhoto = () => {
    setShowAvatarMenu(false);
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') setAvatarUrl(reader.result);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleDeletePhoto = () => {
    setAvatarUrl(null);
    setShowAvatarMenu(false);
  };

  const handleChangePassword = (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordMessage(null);
    if (newPassword !== confirmPassword) {
      setPasswordMessage('error');
      return;
    }
    if (!newPassword.trim()) return;
    if (currentAgentId) {
      updateAgent(currentAgentId, { password: newPassword });
      setNewPassword('');
      setConfirmPassword('');
      setPasswordMessage('success');
    }
  };

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
                  {currentAgent?.id && (
                    <p className="px-3 py-1.5 text-xs text-text-muted font-mono border-b border-border mb-2">
                      Agent ID: {currentAgent.id}
                    </p>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setShowUserMenu(false);
                      setShowProfilePopup(true);
                    }}
                    className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2 text-sm"
                  >
                    <User className="w-4 h-4" />
                    Profile
                  </button>
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

      {showProfilePopup && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40"
            onClick={() => {
              setShowProfilePopup(false);
              setPasswordMessage(null);
            }}
            aria-hidden
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <div
              className="bg-white rounded-xl border border-border shadow-xl w-full max-w-md pointer-events-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                <h2 className="text-lg font-semibold text-text-primary">Profile</h2>
                <button
                  type="button"
                  onClick={() => setShowProfilePopup(false)}
                  className="p-1.5 rounded-lg hover:bg-panel text-text-muted"
                  aria-label="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center gap-6">
                  <div className="relative flex-shrink-0" ref={avatarMenuRef}>
                    <button
                      type="button"
                      data-avatar-trigger
                      onClick={() => setShowAvatarMenu(!showAvatarMenu)}
                      className="relative block w-24 h-24 rounded-full overflow-hidden bg-primary/10 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                      aria-label="Change profile photo"
                    >
                      {avatarUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={avatarUrl} alt="Profile" className="w-full h-full object-cover" />
                      ) : (
                        <span className="w-full h-full flex items-center justify-center text-2xl font-semibold text-primary">
                          {(fullName || '?').charAt(0).toUpperCase()}
                        </span>
                      )}
                      <span className="absolute bottom-0 right-0 w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center shadow">
                        <Camera className="w-4 h-4" />
                      </span>
                    </button>
                    {showAvatarMenu && (
                      <div className="absolute left-0 top-full mt-2 z-20 w-48 bg-white border border-border rounded-xl shadow-xl py-1">
                        <button
                          type="button"
                          onClick={handleChoosePhoto}
                          className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm text-text-primary hover:bg-panel"
                        >
                          <ImagePlus className="w-5 h-5 text-text-muted" />
                          Choose photo
                        </button>
                        {avatarUrl && (
                          <button
                            type="button"
                            onClick={handleDeletePhoto}
                            className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm text-status-error hover:bg-panel"
                          >
                            <Trash2 className="w-5 h-5" />
                            Delete photo
                          </button>
                        )}
                        <div className="border-t border-border my-1" />
                        <button
                          type="button"
                          onClick={() => setShowAvatarMenu(false)}
                          className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm text-text-muted hover:bg-panel"
                        >
                          <X className="w-5 h-5" />
                          Cancel
                        </button>
                      </div>
                    )}
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={handleFileChange}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <label className="block text-sm font-semibold text-text-primary mb-2">Full Name</label>
                    <input
                      type="text"
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary text-text-primary placeholder-text-muted"
                      placeholder="Enter your name"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                    />
                    {currentAgent?.id && (
                      <div className="mt-3">
                        <label className="block text-xs font-semibold text-text-muted mb-1">Agent ID</label>
                        <div className="inline-flex items-center gap-2 px-2 py-1.5 rounded border border-border bg-panel">
                          <code className="text-xs font-mono text-text-primary">{currentAgent.id}</code>
                          <button
                            type="button"
                            onClick={() => navigator.clipboard?.writeText(currentAgent.id)}
                            className="p-1 rounded hover:bg-white text-text-muted"
                            aria-label="Copy agent ID"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                <div className="border-t border-border pt-4">
                  <h3 className="text-sm font-semibold text-text-primary mb-3">Change password</h3>
                  <p className="text-xs text-text-muted mb-3">
                    Your new password will be reflected in the admin panel.
                  </p>
                  <form onSubmit={handleChangePassword} className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-text-primary mb-1">New password</label>
                      <input
                        type="password"
                        value={newPassword}
                        onChange={(e) => { setNewPassword(e.target.value); setPasswordMessage(null); }}
                        placeholder="New password"
                        className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-text-primary mb-1">Confirm new password</label>
                      <input
                        type="password"
                        value={confirmPassword}
                        onChange={(e) => { setConfirmPassword(e.target.value); setPasswordMessage(null); }}
                        placeholder="Confirm new password"
                        className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary text-sm"
                      />
                    </div>
                    {passwordMessage === 'error' && (
                      <p className="text-xs text-status-error">Passwords do not match.</p>
                    )}
                    {passwordMessage === 'success' && (
                      <p className="text-xs text-status-success">Password updated. It will appear in the admin panel.</p>
                    )}
                    <button
                      type="submit"
                      className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors text-sm"
                    >
                      Update password
                    </button>
                  </form>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
