'use client';

import { useState } from 'react';

interface Message {
  id: number;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: string;
}

export function UserChatWindow() {
  const [messages] = useState<Message[]>([
    {
      id: 1,
      content: 'Hello! How can I help you today?',
      sender: 'assistant',
      timestamp: '2 minutes ago',
    },
    {
      id: 2,
      content: 'I need help with my order #12345',
      sender: 'user',
      timestamp: '2 minutes ago',
    },
    {
      id: 3,
      content: 'I can help you with that. Let me check your order status.',
      sender: 'assistant',
      timestamp: '1 minute ago',
    },
    {
      id: 4,
      content: 'Your order is currently in transit and will be delivered within 2-3 business days.',
      sender: 'assistant',
      timestamp: '1 minute ago',
    },
  ]);

  const [inputValue, setInputValue] = useState('');

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-message-bubble rounded-lg p-4 ${
                message.sender === 'user'
                  ? 'bg-primary text-white'
                  : 'bg-panel text-text-primary border border-border'
              }`}
            >
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
            </div>
          </div>
        ))}
      </div>
      
      <div className="border-t border-border px-6 py-4 bg-white">
        <div className="flex items-end gap-3">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 px-4 py-3 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm resize-none min-h-[44px] max-h-32"
            rows={1}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (inputValue.trim()) {
                  // Handle send
                  setInputValue('');
                }
              }
            }}
          />
          <button 
            className="bg-primary text-white px-6 py-3 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={() => {
              if (inputValue.trim()) {
                // Handle send
                setInputValue('');
              }
            }}
            disabled={!inputValue.trim()}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
