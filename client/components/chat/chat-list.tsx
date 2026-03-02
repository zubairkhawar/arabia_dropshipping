'use client';

import { useState } from 'react';
import { useInboxPanels } from '@/contexts/InboxPanelsContext';
import { PanelLeftClose } from 'lucide-react';

interface Conversation {
  id: number;
  customerName: string;
  customerId: string;
  lastMessage: string;
  timestamp: string;
  unread: number;
  channel: 'whatsapp' | 'web' | 'portal';
  status: 'active' | 'resolved' | 'pending';
}

export function ChatList() {
  const inboxPanels = useInboxPanels();
  const [selectedId, setSelectedId] = useState<number | null>(1);
  const [conversations] = useState<Conversation[]>([
    {
      id: 1,
      customerName: 'Ahmed Ali',
      customerId: '#1234',
      lastMessage: 'Hello, I need help with my order...',
      timestamp: '2m ago',
      unread: 2,
      channel: 'whatsapp',
      status: 'active',
    },
    {
      id: 2,
      customerName: 'Sarah Khan',
      customerId: '#1235',
      lastMessage: 'When will my order be delivered?',
      timestamp: '15m ago',
      unread: 0,
      channel: 'web',
      status: 'active',
    },
    {
      id: 3,
      customerName: 'Mohammed Hassan',
      customerId: '#1236',
      lastMessage: 'Thank you for your help!',
      timestamp: '1h ago',
      unread: 0,
      channel: 'portal',
      status: 'resolved',
    },
  ]);

  const channelColors = {
    whatsapp: 'bg-status-success',
    web: 'bg-status-info',
    portal: 'bg-primary',
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-border flex items-center gap-2">
        {inboxPanels && (
          <button
            type="button"
            onClick={inboxPanels.toggleChatList}
            className="rounded p-1.5 text-text-secondary hover:bg-white hover:text-primary transition-colors shrink-0"
            title="Collapse conversation list"
          >
            <PanelLeftClose className="h-5 w-5" />
          </button>
        )}
        <input
          type="text"
          placeholder="Search conversations..."
          className="flex-1 min-w-0 px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
        />
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="p-2 space-y-1">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              onClick={() => setSelectedId(conv.id)}
              className={`p-3 rounded-lg cursor-pointer transition-colors ${
                selectedId === conv.id
                  ? 'bg-primary text-white'
                  : 'bg-white hover:bg-panel border border-border'
              }`}
            >
              <div className="flex items-start justify-between mb-1">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <div className={`w-2 h-2 rounded-full ${channelColors[conv.channel]} flex-shrink-0`} />
                  <span className={`text-sm font-medium truncate ${
                    selectedId === conv.id ? 'text-white' : 'text-text-primary'
                  }`}>
                    {conv.customerName}
                  </span>
                </div>
                <span className={`text-xs flex-shrink-0 ml-2 ${
                  selectedId === conv.id ? 'text-white/80' : 'text-text-muted'
                }`}>
                  {conv.timestamp}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <p className={`text-xs truncate flex-1 ${
                  selectedId === conv.id ? 'text-white/90' : 'text-text-secondary'
                }`}>
                  {conv.lastMessage}
                </p>
                {conv.unread > 0 && (
                  <span className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${
                    selectedId === conv.id
                      ? 'bg-white text-primary'
                      : 'bg-primary text-white'
                  }`}>
                    {conv.unread}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
