'use client';

import { useNotifications } from '@/contexts/NotificationsContext';
import type { AgentNotification } from '@/contexts/NotificationsContext';
import { Bell, ArrowLeft, MessageCircle, User, UserPlus, Mail, MessageSquare } from 'lucide-react';
import Link from 'next/link';

function NotificationIcon({ type }: { type: AgentNotification['type'] }) {
  switch (type) {
    case 'chat_transfer':
      return <MessageCircle className="w-5 h-5 text-primary" />;
    case 'new_lead':
      return <UserPlus className="w-5 h-5 text-primary" />;
    case 'personal_message':
      return <Mail className="w-5 h-5 text-primary" />;
    case 'new_message':
      return <MessageSquare className="w-5 h-5 text-primary" />;
    default:
      return <User className="w-5 h-5 text-primary" />;
  }
}

function formatTime(iso: string) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'Just now';
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (diff < 604800) return d.toLocaleDateString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function AgentSettingsPage() {
  const { getNotificationsForCurrentAgent, markAsRead, markAllAsRead } = useNotifications();
  const list = getNotificationsForCurrentAgent();

  return (
    <div className="flex flex-col h-full bg-white border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-panel shrink-0">
        <div className="flex items-center gap-3">
          <Link
            href="/agent/inbox"
            className="p-2 rounded-lg hover:bg-white border border-border text-text-secondary hover:text-primary transition-colors"
            aria-label="Back to inbox"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex items-center gap-2">
            <Bell className="w-6 h-6 text-primary" />
            <h1 className="text-xl font-semibold text-text-primary">Notifications</h1>
          </div>
        </div>
        {list.some((n) => !n.read) && (
          <button
            type="button"
            onClick={markAllAsRead}
            className="text-sm font-medium text-primary hover:underline"
          >
            Mark all as read
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        {list.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
            <Bell className="w-12 h-12 text-text-muted mb-4" />
            <p className="text-text-secondary font-medium">No notifications yet</p>
            <p className="text-sm text-text-muted mt-1">
              When a chat is transferred to you or you get assigned a conversation, it will show here.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {list.map((n) => (
              <li
                key={n.id}
                className={`px-6 py-4 hover:bg-panel/50 transition-colors cursor-pointer ${
                  !n.read ? 'bg-primary/5' : ''
                }`}
                onClick={() => markAsRead(n.id)}
              >
                <div className="flex gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <NotificationIcon type={n.type} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm ${n.read ? 'text-text-secondary' : 'text-text-primary font-medium'}`}>
                      {n.message}
                    </p>
                    {n.type === 'chat_transfer' && n.description && n.fromAgentName && (
                      <p className="text-xs text-text-muted mt-1">
                        <span className="font-medium text-text-primary">Note from {n.fromAgentName}:</span>{' '}
                        {n.description}
                      </p>
                    )}
                    {n.type !== 'chat_transfer' && n.description && (
                      <p className="text-xs text-text-muted mt-1">{n.description}</p>
                    )}
                    {(n.conversationCustomerName || (n.fromAgentName && n.type !== 'chat_transfer')) && (
                      <p className="text-xs text-text-muted mt-0.5">
                        {n.conversationCustomerName && `Conversation: ${n.conversationCustomerName}`}
                        {n.conversationCustomerName && n.fromAgentName && n.type !== 'chat_transfer' && ' · '}
                        {n.fromAgentName && n.type !== 'chat_transfer' && `From ${n.fromAgentName}`}
                      </p>
                    )}
                    <p className="text-xs text-text-muted mt-1">{formatTime(n.createdAt)}</p>
                  </div>
                  {!n.read && (
                    <span className="w-2 h-2 rounded-full bg-primary flex-shrink-0 mt-2" aria-hidden />
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
