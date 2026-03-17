'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

/** Agent unique ID is set by the backend when the admin creates a new agent. */
export interface AgentRecord {
  id: string;
  email: string;
  name: string;
  /**
   * Initial password set by the admin. Only stored on the client for convenience when
   * creating a new agent – the backend never returns plaintext passwords.
   */
  password: string;
  avatarUrl: string | null;
}

interface AgentsContextType {
  agents: AgentRecord[];
  currentAgentId: string | null;
  setCurrentAgentId: (id: string | null) => void;
  getCurrentAgent: () => AgentRecord | null;
  addAgent: (email: string, name: string, password: string) => Promise<void>;
  updateAgent: (id: string, updates: Partial<Pick<AgentRecord, 'name' | 'password' | 'avatarUrl'>>) => Promise<void>;
  removeAgent: (id: string) => Promise<void>;
}

const AgentsContext = createContext<AgentsContextType | undefined>(undefined);

// FastAPI backend base URL; in production set NEXT_PUBLIC_API_BASE_URL to override.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
// For now we operate on the default tenant created by the backend.
const DEFAULT_TENANT_ID = 1;

interface AgentApiModel {
  id: number;
  tenant_id: number;
  user_id: number;
  email: string;
  full_name: string | null;
  status: string;
  team: string | null;
}

export function AgentsProvider({ children }: { children: ReactNode }) {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [currentAgentId, setCurrentAgentId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadAgents = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/agents?tenant_id=${DEFAULT_TENANT_ID}`, {
          method: 'GET',
        });
        if (!res.ok) {
          return;
        }
        const data = (await res.json()) as AgentApiModel[];
        if (cancelled) return;
        const mapped: AgentRecord[] = data.map((a) => ({
          id: String(a.id),
          email: a.email,
          name: a.full_name || a.email.split('@')[0] || 'Agent',
          password: '',
          avatarUrl: null,
        }));
        setAgents(mapped);
        if (!currentAgentId && mapped.length > 0) {
          setCurrentAgentId(mapped[0].id);
        }
      } catch {
        // Silent failure to avoid impacting UI performance.
      }
    };

    loadAgents();
    return () => {
      cancelled = true;
    };
  }, [currentAgentId]);

  const getCurrentAgent = useCallback(() => {
    if (!currentAgentId) return null;
    return agents.find((a) => a.id === currentAgentId) ?? null;
  }, [agents, currentAgentId]);

  const addAgent = useCallback(
    async (email: string, name: string, password: string) => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/agents`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            email,
            password,
            full_name: name,
            tenant_id: DEFAULT_TENANT_ID,
          }),
        });
        if (!res.ok) {
          return;
        }
        const created = (await res.json()) as AgentApiModel;
        const record: AgentRecord = {
          id: String(created.id),
          email: created.email,
          name: created.full_name || name,
          password,
          avatarUrl: null,
        };
        setAgents((prev) => [...prev, record]);
        setCurrentAgentId(String(created.id));
      } catch {
        // Ignore errors here; calling components can surface generic toasts if needed.
      }
    },
    [],
  );

  const updateAgent = useCallback(
    async (id: string, updates: Partial<Pick<AgentRecord, 'name' | 'password' | 'avatarUrl'>>) => {
      const numericId = Number(id);
      if (!Number.isFinite(numericId)) return;

      // Optimistic UI update.
      setAgents((prev) => prev.map((a) => (a.id === id ? { ...a, ...updates } : a)));

      const payload: { full_name?: string; avatar_url?: string | null } = {};
      if (updates.name !== undefined) payload.full_name = updates.name;
      if (updates.avatarUrl !== undefined) payload.avatar_url = updates.avatarUrl;

      if (Object.keys(payload).length === 0) {
        return;
      }

      try {
        await fetch(`${API_BASE_URL}/api/agents/${numericId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });
      } catch {
        // On failure we leave the optimistic state; admin can refresh if needed.
      }
    },
    [],
  );

  const removeAgent = useCallback(
    async (id: string) => {
      const numericId = Number(id);
      if (!Number.isFinite(numericId)) return;

      // Optimistic removal.
      setAgents((prev) => prev.filter((a) => a.id !== id));
      setCurrentAgentId((prev) => {
        if (prev !== id) return prev;
        const remaining = agents.filter((a) => a.id !== id);
        return remaining[0]?.id ?? null;
      });

      try {
        await fetch(`${API_BASE_URL}/api/agents/${numericId}`, {
          method: 'DELETE',
        });
      } catch {
        // Ignore; deletion will be consistent after a refresh.
      }
    },
    [agents],
  );

  return (
    <AgentsContext.Provider
      value={{
        agents,
        currentAgentId,
        setCurrentAgentId,
        getCurrentAgent,
        addAgent,
        updateAgent,
        removeAgent,
      }}
    >
      {children}
    </AgentsContext.Provider>
  );
}

export function useAgents() {
  const context = useContext(AgentsContext);
  if (context === undefined) {
    return {
      agents: [] as AgentRecord[],
      currentAgentId: null as string | null,
      setCurrentAgentId: () => {},
      getCurrentAgent: () => null,
      addAgent: async () => {},
      updateAgent: async () => {},
      removeAgent: async () => {},
    };
  }
  return context;
}
