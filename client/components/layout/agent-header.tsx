'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { Search, Bell, User, ChevronDown, LogOut, KeyRound, PanelRightOpen, PanelLeftClose, Camera, ImagePlus, Trash2, X, Copy, Eye, EyeOff } from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import { useAgentProfile } from '@/contexts/AgentProfileContext';
import { useAgents } from '@/contexts/AgentsContext';
import { useAgentPresence, getSlugByName } from '@/contexts/AgentPresenceContext';
import { useOnlineSchedule } from '@/contexts/OnlineScheduleContext';
import { useNotifications } from '@/contexts/NotificationsContext';
import { useToast } from '@/contexts/ToastContext';
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
  const [showChangePasswordPopup, setShowChangePasswordPopup] = useState(false);
  const [showAvatarMenu, setShowAvatarMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const avatarMenuRef = useRef<HTMLDivElement>(null);
  const { isCollapsed, toggleSidebar } = useSidebar();
  const { avatarUrl, fullName, setAvatarUrl, setFullName } = useAgentProfile();
  const { currentAgentId, updateAgent, getCurrentAgent } = useAgents();
  const currentAgent = getCurrentAgent();
  const { getPresence, setPresence } = useAgentPresence();
  const { isWithinSchedule, schedule } = useOnlineSchedule();
  const slug = getSlugByName(fullName);
  const rawStatus = slug ? getPresence(slug) : 'offline';
  const agentStatus: AgentStatus = isWithinSchedule() ? rawStatus : 'offline';
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<'success' | 'error' | 'wrong_old' | null>(null);
  const { toast } = useToast();
  const pathname = usePathname();
  const displayName = fullName || userName || 'Support Agent';
  const {
    getNotificationsForCurrentAgent,
    unreadCount,
    markAsRead,
  } = useNotifications();
  const notificationList = getNotificationsForCurrentAgent();

  const formatNotifTime = (iso: string) => {
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

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
    if (currentAgent?.password != null && oldPassword !== currentAgent.password) {
      setPasswordMessage('wrong_old');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordMessage('error');
      return;
    }
    if (!newPassword.trim()) return;
    if (currentAgentId) {
      updateAgent(currentAgentId, { password: newPassword });
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordMessage('success');
      setShowChangePasswordPopup(false);
      toast('Password changed successfully');
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
                {(Object.keys(statusConfig) as AgentStatus[]).map((status) => {
                  const disabled = status === 'active' && !isWithinSchedule();
                  return (
                    <button
                      key={status}
                      onClick={() => {
                        if (disabled) return;
                        if (slug) setPresence(slug, status);
                        setShowStatusMenu(false);
                      }}
                      disabled={disabled}
                      title={
                        disabled
                          ? `You can only go online during working hours (${schedule.startTime}–${schedule.endTime}, selected days)`
                          : undefined
                      }
                      className={`w-full flex items-center gap-2 px-4 py-2 text-left text-sm ${
                        disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-panel'
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${statusConfig[status].dotClass}`} />
                      {statusConfig[status].label}
                    </button>
                  );
                })}
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
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 min-w-[0.5rem] h-2 px-1 flex items-center justify-center bg-primary rounded-full text-[10px] font-semibold text-white">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>
          {showNotifications && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowNotifications(false)} />
              <div className="absolute right-0 mt-2 w-80 bg-white border border-border rounded-lg shadow-xl z-20 flex flex-col max-h-[28rem]">
                <div className="p-4 border-b border-border shrink-0">
                  <h3 className="font-semibold text-text-primary">Notifications</h3>
                </div>
                <div className="overflow-y-auto flex-1 min-h-0">
                  {notificationList.length === 0 ? (
                    <div className="p-4 text-sm text-text-muted">No notifications yet.</div>
                  ) : (
                    notificationList.slice(0, 10).map((n) => (
                      <div
                        key={n.id}
                        onClick={() => markAsRead(n.id)}
                        className={`p-4 border-b border-border hover:bg-panel cursor-pointer ${!n.read ? 'bg-primary/5' : ''}`}
                      >
                        <p className="text-sm text-text-primary">{n.message}</p>
                        {n.type === 'chat_transfer' && n.description && n.fromAgentName ? (
                          <p className="text-xs text-text-muted mt-0.5">
                            <span className="font-medium text-text-primary">Note from {n.fromAgentName}:</span>{' '}
                            {n.description}
                          </p>
                        ) : (
                          n.description && <p className="text-xs text-text-muted mt-0.5">{n.description}</p>
                        )}
                        <p className="text-xs text-text-muted mt-1">{formatNotifTime(n.createdAt)}</p>
                      </div>
                    ))
                  )}
                </div>
                <div className="p-2 border-t border-border shrink-0">
                  <Link
                    href="/agent/settings"
                    onClick={() => setShowNotifications(false)}
                    className="block w-full text-center py-2 text-sm font-medium text-primary hover:underline rounded-lg hover:bg-panel"
                  >
                    Show all notifications
                  </Link>
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
              <div className="absolute right-0 mt-2 w-52 min-w-[10rem] bg-white border border-border rounded-lg shadow-xl z-20">
                <div className="p-2">
                  <button
                    type="button"
                    onClick={() => {
                      setShowUserMenu(false);
                      setShowProfilePopup(true);
                    }}
                    className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2 text-sm"
                  >
                    <User className="w-4 h-4 flex-shrink-0" />
                    Profile
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowUserMenu(false);
                      setShowChangePasswordPopup(true);
                    }}
                    className="w-full text-left px-4 py-2 rounded-lg hover:bg-panel text-text-primary flex items-center gap-2 text-sm whitespace-nowrap"
                  >
                    <KeyRound className="w-4 h-4 flex-shrink-0" />
                    Change password
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
              className="bg-white rounded-xl border border-border shadow-xl w-full max-w-md pointer-events-auto max-h-[90vh] overflow-y-auto"
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
                {/* Big avatar centered */}
                <div className="relative flex justify-center" ref={avatarMenuRef}>
                  <button
                    type="button"
                    data-avatar-trigger
                    onClick={() => setShowAvatarMenu(!showAvatarMenu)}
                    className="relative block w-44 h-44 rounded-full overflow-hidden bg-primary/10 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                    aria-label="Change profile photo"
                  >
                    {avatarUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={avatarUrl} alt="Profile" className="w-full h-full object-cover" />
                    ) : (
                      <span className="w-full h-full flex items-center justify-center text-5xl font-semibold text-primary">
                        {(fullName || '?').charAt(0).toUpperCase()}
                      </span>
                    )}
                    <span className="absolute bottom-0 right-0 w-9 h-9 rounded-full bg-primary text-white flex items-center justify-center shadow">
                      <Camera className="w-4 h-4" />
                    </span>
                  </button>
                  {showAvatarMenu && (
                    <div className="absolute left-1/2 -translate-x-1/2 top-full mt-2 z-20 w-48 bg-white border border-border rounded-xl shadow-xl py-1">
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
                {/* Name and Agent ID on same row; below it Email */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <label className="block text-xs font-semibold text-text-muted mb-1">Name</label>
                      <input
                        type="text"
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary text-text-primary placeholder-text-muted text-sm"
                        placeholder="Enter your name"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                      />
                    </div>
                    {currentAgent?.id && (
                      <div className="flex-shrink-0">
                        <label className="block text-xs font-semibold text-text-muted mb-1">Agent ID</label>
                        <div className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-panel">
                          <code className="text-sm font-mono text-text-primary">{currentAgent.id}</code>
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
                  {currentAgent?.email && (
                    <div>
                      <label className="block text-xs font-semibold text-text-muted mb-1">Email</label>
                      <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border bg-panel">
                        <span className="text-sm text-text-primary truncate">{currentAgent.email}</span>
                        <button
                          type="button"
                          onClick={() => navigator.clipboard?.writeText(currentAgent.email)}
                          className="p-1 rounded hover:bg-white text-text-muted flex-shrink-0"
                          aria-label="Copy email"
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {showChangePasswordPopup && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40"
            onClick={() => {
              setShowChangePasswordPopup(false);
              setPasswordMessage(null);
              setOldPassword('');
            }}
            aria-hidden
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <div
              className="bg-white rounded-xl border border-border shadow-xl w-full max-w-lg pointer-events-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                <h2 className="text-lg font-semibold text-text-primary">Change password</h2>
                <button
                  type="button"
                  onClick={() => {
                    setShowChangePasswordPopup(false);
                    setPasswordMessage(null);
                    setOldPassword('');
                  }}
                  className="p-1.5 rounded-lg hover:bg-panel text-text-muted"
                  aria-label="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6">
                <form onSubmit={handleChangePassword} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-text-primary mb-1">Old password</label>
                    <input
                      type="text"
                      value={oldPassword}
                      onChange={(e) => { setOldPassword(e.target.value); setPasswordMessage(null); }}
                      placeholder="Old password"
                      className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-text-primary mb-1">New password</label>
                    <div className="relative">
                      <input
                        type={showNewPassword ? 'text' : 'password'}
                        value={newPassword}
                        onChange={(e) => { setNewPassword(e.target.value); setPasswordMessage(null); }}
                        placeholder="New password"
                        className="w-full px-3 py-2 pr-10 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPassword((v) => !v)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-text-muted hover:text-text-primary"
                        aria-label={showNewPassword ? 'Hide password' : 'Show password'}
                      >
                        {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-text-primary mb-1">Confirm new password</label>
                    <div className="relative">
                      <input
                        type={showConfirmPassword ? 'text' : 'password'}
                        value={confirmPassword}
                        onChange={(e) => { setConfirmPassword(e.target.value); setPasswordMessage(null); }}
                        placeholder="Confirm new password"
                        className="w-full px-3 py-2 pr-10 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword((v) => !v)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-text-muted hover:text-text-primary"
                        aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                      >
                        {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                  {passwordMessage === 'wrong_old' && (
                    <p className="text-xs text-status-error">Current password is incorrect.</p>
                  )}
                  {passwordMessage === 'error' && (
                    <p className="text-xs text-status-error">Passwords do not match.</p>
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
        </>
      )}
    </div>
  );
}
