'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

const STORAGE_KEY = 'dm-chats';

export interface DmConversation {
  slug: string;
  name: string;
  lastMessageAt: string;
}

interface DmChatsContextType {
  conversations: DmConversation[];
  addOrUpdateConversation: (slug: string, name: string) => void;
  removeConversation: (slug: string) => void;
  getConversations: () => DmConversation[];
}

function loadFromStorage(): DmConversation[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveToStorage(conversations: DmConversation[]) {
  try {
    if (typeof window !== 'undefined') {
      const sorted = [...conversations].sort(
        (a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime(),
      );
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sorted));
    }
  } catch {
    // ignore
  }
}

const DmChatsContext = createContext<DmChatsContextType | undefined>(undefined);

export function DmChatsProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<DmConversation[]>([]);

  useEffect(() => {
    setConversations(loadFromStorage());
  }, []);

  const addOrUpdateConversation = useCallback((slug: string, name: string) => {
    const now = new Date().toISOString();
    setConversations((prev) => {
      const rest = prev.filter((c) => c.slug !== slug);
      const updated: DmConversation[] = [
        { slug, name, lastMessageAt: now },
        ...rest,
      ].sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime());
      saveToStorage(updated);
      return updated;
    });
  }, []);

  const removeConversation = useCallback((slug: string) => {
    setConversations((prev) => {
      const updated = prev.filter((c) => c.slug !== slug);
      saveToStorage(updated);
      return updated;
    });
  }, []);

  const getConversations = useCallback(() => conversations, [conversations]);

  return (
    <DmChatsContext.Provider
      value={{
        conversations,
        addOrUpdateConversation,
        removeConversation,
        getConversations,
      }}
    >
      {children}
    </DmChatsContext.Provider>
  );
}

export function useDmChats() {
  const context = useContext(DmChatsContext);
  if (context === undefined) {
    return {
      conversations: [] as DmConversation[],
      addOrUpdateConversation: () => {},
      removeConversation: () => {},
      getConversations: () => [] as DmConversation[],
    };
  }
  return context;
}
