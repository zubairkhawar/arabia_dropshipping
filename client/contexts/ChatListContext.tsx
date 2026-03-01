'use client';

import React, { createContext, useContext, useState, ReactNode } from 'react';

interface ChatListContextType {
  isCollapsed: boolean;
  toggleChatList: () => void;
}

const ChatListContext = createContext<ChatListContextType | undefined>(undefined);

export function ChatListProvider({ children }: { children: ReactNode }) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const toggleChatList = () => {
    setIsCollapsed(!isCollapsed);
  };

  return (
    <ChatListContext.Provider value={{ isCollapsed, toggleChatList }}>
      {children}
    </ChatListContext.Provider>
  );
}

export function useChatList() {
  const context = useContext(ChatListContext);
  if (context === undefined) {
    throw new Error('useChatList must be used within a ChatListProvider');
  }
  return context;
}
