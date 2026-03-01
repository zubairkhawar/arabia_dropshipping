'use client';

import { ChatList } from '@/components/chat/chat-list';
import { ChatWindow } from '@/components/chat/chat-window';

export default function UserChat() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Chat Inbox</h1>
        <p className="text-text-secondary mt-1">View your customer conversations</p>
      </div>
      
      <div className="flex h-[calc(100vh-12rem)] border border-border rounded-lg overflow-hidden bg-white">
        <div className="hidden md:block w-chatlist-tablet lg:w-chatlist-laptop xl:w-chatlist-desktop 2xl:w-chatlist-ultrawide border-r border-border bg-panel">
          <ChatList />
        </div>
        <div className="flex-1 flex flex-col">
          <ChatWindow />
        </div>
      </div>
    </div>
  );
}
