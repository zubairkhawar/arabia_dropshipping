'use client';

import { useState } from 'react';
import { Plus, Search } from 'lucide-react';

interface Chat {
  id: number;
  title: string;
}

export function UserChatList() {
  const [selectedId, setSelectedId] = useState<number | null>(3);
  const [chats] = useState<Chat[]>([
    { id: 1, title: 'AI Bot Platform Design' },
    { id: 2, title: 'Authority letter for documents' },
    { id: 3, title: 'WATI WooCommerce Order A...' },
    { id: 4, title: 'Automation Workflow Design' },
    { id: 5, title: 'Fiverr STT Bot Reply' },
    { id: 6, title: 'AWS server cost estimation' },
    { id: 7, title: 'Fiverr Account Issues' },
  ]);

  const handleNewChat = () => {
    // Handle new chat creation
    console.log('New chat');
  };

  const handleSearch = () => {
    // Handle search
    console.log('Search');
  };

  return (
    <div className="flex flex-col h-full bg-white">
      {/* New Chat Button */}
      <div className="p-4 border-b border-border">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </div>

      {/* Search Button */}
      <div className="p-4 border-b border-border">
        <button
          onClick={handleSearch}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-border rounded-lg hover:bg-panel transition-colors text-sm text-text-secondary"
        >
          <Search className="w-4 h-4" />
          Search
        </button>
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-2">
          {chats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => setSelectedId(chat.id)}
              className={`w-full text-left px-3 py-2 rounded-lg transition-colors mb-1 ${
                selectedId === chat.id
                  ? 'bg-panel text-text-primary'
                  : 'text-text-primary hover:bg-panel'
              }`}
            >
              <p className="text-sm truncate">{chat.title}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
