'use client';

import React, { createContext, useContext, useMemo, useState } from 'react';

type AgentSearchContextType = {
  inboxQuery: string;
  setInboxQuery: React.Dispatch<React.SetStateAction<string>>;
};

const AgentSearchContext = createContext<AgentSearchContextType | null>(null);

export function AgentSearchProvider({ children }: { children: React.ReactNode }) {
  const [inboxQuery, setInboxQuery] = useState('');
  const value = useMemo(() => ({ inboxQuery, setInboxQuery }), [inboxQuery]);
  return <AgentSearchContext.Provider value={value}>{children}</AgentSearchContext.Provider>;
}

export function useAgentSearch() {
  const ctx = useContext(AgentSearchContext);
  if (!ctx) {
    return {
      inboxQuery: '',
      setInboxQuery: (_: React.SetStateAction<string>) => {},
    };
  }
  return ctx;
}
