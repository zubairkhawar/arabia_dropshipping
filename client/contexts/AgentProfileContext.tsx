'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

const STORAGE_AVATAR = 'agent-profile-avatar';
const STORAGE_NAME = 'agent-profile-name';

interface AgentProfileContextType {
  avatarUrl: string | null;
  fullName: string;
  setAvatarUrl: (url: string | null) => void;
  setFullName: (name: string) => void;
}

const AgentProfileContext = createContext<AgentProfileContextType | undefined>(undefined);

export function AgentProfileProvider({ children }: { children: ReactNode }) {
  const [avatarUrl, setAvatarUrlState] = useState<string | null>(null);
  const [fullName, setFullNameState] = useState<string>('');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const stored = localStorage.getItem(STORAGE_AVATAR);
      if (stored) setAvatarUrlState(stored);
      const name = localStorage.getItem(STORAGE_NAME);
      if (name) setFullNameState(name);
    } catch {
      // ignore
    }
  }, []);

  const setAvatarUrl = useCallback((url: string | null) => {
    setAvatarUrlState(url);
    try {
      if (typeof window !== 'undefined') {
        if (url) localStorage.setItem(STORAGE_AVATAR, url);
        else localStorage.removeItem(STORAGE_AVATAR);
      }
    } catch {
      // ignore
    }
  }, []);

  const setFullName = useCallback((name: string) => {
    setFullNameState(name);
    try {
      if (typeof window !== 'undefined') {
        if (name) localStorage.setItem(STORAGE_NAME, name);
        else localStorage.removeItem(STORAGE_NAME);
      }
    } catch {
      // ignore
    }
  }, []);

  return (
    <AgentProfileContext.Provider
      value={{
        avatarUrl,
        fullName: fullName || 'Support Agent',
        setAvatarUrl,
        setFullName,
      }}
    >
      {children}
    </AgentProfileContext.Provider>
  );
}

export function useAgentProfile() {
  const context = useContext(AgentProfileContext);
  if (context === undefined) {
    return {
      avatarUrl: null as string | null,
      fullName: '',
      setAvatarUrl: (_url: string | null) => {},
      setFullName: (_name: string) => {},
    };
  }
  return context;
}
