'use client';

import React, { createContext, useContext, ReactNode } from 'react';
import { useAgents } from '@/contexts/AgentsContext';

interface AgentProfileContextType {
  avatarUrl: string | null;
  fullName: string;
  setAvatarUrl: (url: string | null) => void;
  setFullName: (name: string) => void;
}

const AgentProfileContext = createContext<AgentProfileContextType | undefined>(undefined);

export function AgentProfileProvider({ children }: { children: ReactNode }) {
  const { getCurrentAgent, updateAgent, currentAgentId } = useAgents();
  const agent = getCurrentAgent();

  const fullName = agent?.name ?? '';
  const avatarUrl = agent?.avatarUrl ?? null;

  const setFullName = (name: string) => {
    if (currentAgentId) updateAgent(currentAgentId, { name });
  };

  const setAvatarUrl = (url: string | null) => {
    if (currentAgentId) updateAgent(currentAgentId, { avatarUrl: url });
  };

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
