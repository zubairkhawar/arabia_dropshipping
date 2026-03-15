'use client';

import { createContext, useContext, useState, type ReactNode } from 'react';

interface InboxPanelsContextType {
  chatListCollapsed: boolean;
  contextCollapsed: boolean;
  setChatListCollapsed: (value: boolean) => void;
  setContextCollapsed: (value: boolean) => void;
  toggleChatList: () => void;
  toggleContext: () => void;
}

const InboxPanelsContext = createContext<InboxPanelsContextType | undefined>(undefined);

export function InboxPanelsProvider({ children }: { children: ReactNode }) {
  const [chatListCollapsed, setChatListCollapsed] = useState(false);
  const [contextCollapsed, setContextCollapsed] = useState(false);

  const toggleChatList = () => setChatListCollapsed((prev) => !prev);
  const toggleContext = () => setContextCollapsed((prev) => !prev);

  return (
    <InboxPanelsContext.Provider
      value={{
        chatListCollapsed,
        contextCollapsed,
        setChatListCollapsed,
        setContextCollapsed,
        toggleChatList,
        toggleContext,
      }}
    >
      {children}
    </InboxPanelsContext.Provider>
  );
}

export function useInboxPanels(): InboxPanelsContextType {
  const value = useContext(InboxPanelsContext);
  if (value === undefined) {
    throw new Error('useInboxPanels must be used within InboxPanelsProvider');
  }
  return value;
}
