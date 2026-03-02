'use client';

import { useState } from 'react';
import { ArrowRightLeft, Bot, AlertCircle } from 'lucide-react';

interface Message {
  id: number;
  content: string;
  sender: 'customer' | 'agent' | 'ai';
  senderName: string;
  timestamp: string;
}

export interface ChatWindowProps {
  isInternalChat?: boolean;
  title?: string;
  subtitle?: string;
  showTransferControls?: boolean;
}

const defaultCustomerMessages: Message[] = [
  { id: 1, content: 'Hello! How can I help you today?', sender: 'ai', senderName: 'AI Assistant', timestamp: '2 minutes ago' },
  { id: 2, content: 'I need help with my order #12345', sender: 'customer', senderName: 'Ahmed Ali', timestamp: '2 minutes ago' },
  { id: 3, content: 'I can help you with that. Let me check your order status.', sender: 'ai', senderName: 'AI Assistant', timestamp: '1 minute ago' },
  { id: 4, content: 'Your order is currently in transit and will be delivered within 2-3 business days.', sender: 'ai', senderName: 'AI Assistant', timestamp: '1 minute ago' },
];

export function ChatWindow({
  isInternalChat = false,
  title = 'Ahmed Ali',
  subtitle = 'Store: My Shopify Store • Order #12345',
  showTransferControls = false,
}: ChatWindowProps = {}) {
  const [messages] = useState<Message[]>(defaultCustomerMessages);

  const [inputValue, setInputValue] = useState('');

  const getMessageStyle = (sender: string) => {
    if (sender === 'customer') {
      return 'bg-chat-user text-white';
    } else if (sender === 'agent') {
      return 'bg-chat-agent text-text-primary';
    } else {
      return 'bg-chat-ai text-text-primary';
    }
  };

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="h-chat-header border-b border-border px-6 flex items-center justify-between bg-white shrink-0">
        <div>
          {isInternalChat && (
            <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-primary border border-primary rounded px-2 py-0.5 mb-1.5">
              Internal Chat
            </span>
          )}
          <h3 className="font-medium text-text-primary">{title}</h3>
          <p className="text-xs text-text-secondary">{subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          {!isInternalChat && (
            <span className="text-xs px-2 py-1 bg-status-success text-white rounded">WhatsApp</span>
          )}
          {showTransferControls && (
            <>
              <button
                type="button"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-white hover:bg-panel text-text-secondary hover:text-primary text-xs font-medium transition-colors"
                title="Transfer to another agent or team"
              >
                <ArrowRightLeft className="w-4 h-4" />
                Transfer
              </button>
              <button
                type="button"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-white hover:bg-panel text-text-secondary hover:text-primary text-xs font-medium transition-colors"
                title="Send conversation back to AI bot"
              >
                <Bot className="w-4 h-4" />
                Send to AI
              </button>
              <button
                type="button"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-white hover:bg-panel text-status-warning hover:bg-status-warning/10 text-xs font-medium transition-colors"
                title="Escalate to supervisor"
              >
                <AlertCircle className="w-4 h-4" />
                Escalate
              </button>
            </>
          )}
          <button className="text-text-secondary hover:text-text-primary p-1.5 rounded">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
          </button>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-panel">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.sender === 'customer' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`max-w-message-bubble rounded-lg p-3 ${getMessageStyle(message.sender)}`}>
              {message.sender !== 'customer' && (
                <p className="text-xs font-medium mb-1 opacity-75">{message.senderName}</p>
              )}
              <p className={`text-sm ${message.sender === 'customer' ? 'text-white' : 'text-text-primary'}`}>
                {message.content}
              </p>
              <span className={`text-xs mt-1 block ${
                message.sender === 'customer' ? 'text-white/75' : 'text-text-muted'
              }`}>
                {message.timestamp}
              </span>
            </div>
          </div>
        ))}
      </div>
      
      <div className="h-message-input border-t border-border px-6 py-4 flex items-center gap-3 bg-white">
        <button className="text-text-secondary hover:text-text-primary">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
          </svg>
        </button>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Type a message..."
          className="flex-1 px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
          onKeyPress={(e) => {
            if (e.key === 'Enter' && inputValue.trim()) {
              // Handle send
              setInputValue('');
            }
          }}
        />
        <button 
          className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium"
          onClick={() => {
            if (inputValue.trim()) {
              // Handle send
              setInputValue('');
            }
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
