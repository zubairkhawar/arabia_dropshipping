'use client';

import { UserChatList } from '@/components/chat/user-chat-list';
import { UserChatWindow } from '@/components/chat/user-chat-window';
import { ChatListProvider, useChatList } from '@/contexts/ChatListContext';
import { Menu, X } from 'lucide-react';

function UserChatContent() {
  const { isCollapsed, toggleChatList } = useChatList();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Chat Inbox</h1>
        <p className="text-text-secondary mt-1">Chat with AI assistant</p>
      </div>
      
      <div className="flex h-[calc(100vh-12rem)] border border-border rounded-lg overflow-hidden bg-white">
        {!isCollapsed && (
          <div className="hidden md:block w-chatlist-tablet lg:w-chatlist-laptop xl:w-chatlist-desktop 2xl:w-chatlist-ultrawide border-r border-border bg-white">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold text-text-primary text-sm">Your chats</h2>
              <button
                onClick={toggleChatList}
                className="p-1 rounded hover:bg-panel transition-colors"
              >
                <X className="w-4 h-4 text-text-secondary" />
              </button>
            </div>
            <UserChatList />
          </div>
        )}
        <div className="flex-1 flex flex-col relative">
          {isCollapsed && (
            <button
              onClick={toggleChatList}
              className="absolute left-4 top-4 z-10 p-2 bg-white border border-border rounded-lg shadow-sm hover:bg-panel transition-colors"
            >
              <Menu className="w-5 h-5 text-text-secondary" />
            </button>
          )}
          <UserChatWindow />
        </div>
      </div>
    </div>
  );
}

export default function UserChat() {
  return (
    <ChatListProvider>
      <UserChatContent />
    </ChatListProvider>
  );
}
