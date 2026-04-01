'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

/** Agent unique ID is set by the backend when the admin creates a new agent. */
export interface AgentRecord {
  id: string;
  email: string;
  name: string;
  status: 'online' | 'busy' | 'offline';
  /**
   * Initial password set by the admin. Only stored on the client for convenience when
   * creating a new agent – the backend never returns plaintext passwords.
   */
  password: string;
  avatarUrl: string | null;
  createdAt: string;
}

interface AgentsContextType {
  agents: AgentRecord[];
  currentAgentId: string | null;
  setCurrentAgentId: (id: string | null) => void;
  getCurrentAgent: () => AgentRecord | null;
  addAgent: (email: string, name: string, password: string) => Promise<boolean>;
  updateAgent: (id: string, updates: Partial<Pick<AgentRecord, 'name' | 'password' | 'avatarUrl'>>) => Promise<boolean>;
  removeAgent: (id: string) => Promise<boolean>;
  setAgentStatus: (id: string, status: 'online' | 'busy' | 'offline') => Promise<boolean>;
}

const AgentsContext = createContext<AgentsContextType | undefined>(undefined);
const AGENT_PASSWORDS_STORAGE_KEY = 'agent-passwords';
const AUTH_EMAIL_STORAGE_KEY = 'auth_email';

// Keep consistent with the rest of the frontend config.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
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
  created_at: string;
}

function normalizeAgentStatus(value: string | null | undefined): 'online' | 'busy' | 'offline' {
  if (value === 'online' || value === 'busy') return value;
  return 'offline';
}

function loadStoredPasswords(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(AGENT_PASSWORDS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, string>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveStoredPasswords(passwords: Record<string, string>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(AGENT_PASSWORDS_STORAGE_KEY, JSON.stringify(passwords));
  } catch {
    // Ignore localStorage write failures.
  }
}

export function AgentsProvider({ children }: { children: ReactNode }) {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [currentAgentId, setCurrentAgentId] = useState<string | null>(null);

  const refreshAgents = useCallback(async () => {
    const res = await fetch(`${API_BASE_URL}/api/agents?tenant_id=${DEFAULT_TENANT_ID}`, {
      method: 'GET',
    });
    if (!res.ok) {
      return false;
    }
    const data = (await res.json()) as AgentApiModel[];
    const storedPasswords = loadStoredPasswords();
    const mapped: AgentRecord[] = data.map((a) => ({
      id: String(a.id),
      email: a.email,
      name: a.full_name || a.email.split('@')[0] || 'Agent',
      status: normalizeAgentStatus(a.status),
      password: storedPasswords[String(a.id)] ?? '',
      avatarUrl: null,
      createdAt: a.created_at,
    }));
    setAgents(mapped);
    const authEmail =
      typeof window !== 'undefined'
        ? (localStorage.getItem(AUTH_EMAIL_STORAGE_KEY) || '').trim().toLowerCase()
        : '';
    setCurrentAgentId((prev) => {
      const byEmail = authEmail
        ? mapped.find((a) => a.email.trim().toLowerCase() === authEmail)?.id ?? null
        : null;
      if (byEmail) return byEmail;
      // If an auth email exists but doesn't map to an agent row, don't silently
      // switch to another agent account.
      if (authEmail) return null;
      if (prev && mapped.some((a) => a.id === prev)) return prev;
      return mapped[0]?.id ?? null;
    });
    return true;
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const ok = await refreshAgents();
        if (!ok || cancelled) return;
      } catch {
        // Silent failure to avoid impacting UI performance.
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [refreshAgents]);

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
          return false;
        }
        const created = (await res.json()) as AgentApiModel;
        const record: AgentRecord = {
          id: String(created.id),
          email: created.email,
          name: created.full_name || name,
          status: normalizeAgentStatus(created.status),
          password,
          avatarUrl: null,
          createdAt: created.created_at,
        };
        const storedPasswords = loadStoredPasswords();
        storedPasswords[String(created.id)] = password;
        saveStoredPasswords(storedPasswords);
        setAgents((prev) => [...prev, record]);
        setCurrentAgentId(String(created.id));
        return true;
      } catch {
        return false;
      }
    },
    [],
  );

  const updateAgent = useCallback(
    async (id: string, updates: Partial<Pick<AgentRecord, 'name' | 'password' | 'avatarUrl'>>) => {
      const numericId = Number(id);
      if (!Number.isFinite(numericId)) return false;

      // Optimistic UI update.
      setAgents((prev) => prev.map((a) => (a.id === id ? { ...a, ...updates } : a)));
      if (updates.password !== undefined) {
        const storedPasswords = loadStoredPasswords();
        storedPasswords[id] = updates.password;
        saveStoredPasswords(storedPasswords);
      }

      const payload: { full_name?: string; avatar_url?: string | null } = {};
      if (updates.name !== undefined) payload.full_name = updates.name;
      if (updates.avatarUrl !== undefined) payload.avatar_url = updates.avatarUrl;

      if (Object.keys(payload).length === 0) {
        return true;
      }

      try {
        const res = await fetch(`${API_BASE_URL}/api/agents/${numericId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });
        if (!res.ok) return false;
        return true;
      } catch {
        return false;
      }
    },
    [],
  );

  const removeAgent = useCallback(
    async (id: string) => {
      const numericId = Number(id);
      if (!Number.isFinite(numericId)) return false;

      // Optimistic removal.
      setAgents((prev) => prev.filter((a) => a.id !== id));
      const storedPasswords = loadStoredPasswords();
      if (storedPasswords[id] !== undefined) {
        delete storedPasswords[id];
        saveStoredPasswords(storedPasswords);
      }
      setCurrentAgentId((prev) => {
        if (prev !== id) return prev;
        const remaining = agents.filter((a) => a.id !== id);
        return remaining[0]?.id ?? null;
      });

      try {
        const res = await fetch(`${API_BASE_URL}/api/agents/${numericId}`, {
          method: 'DELETE',
        });
        if (!res.ok) return false;
        return true;
      } catch {
        return false;
      }
    },
    [agents],
  );

  const setAgentStatus = useCallback(
    async (id: string, status: 'online' | 'busy' | 'offline') => {
      const numericId = Number(id);
      if (!Number.isFinite(numericId)) return false;
      try {
        const res = await fetch(`${API_BASE_URL}/api/routing/agents/${numericId}/status`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ status }),
        });
        if (!res.ok) return false;
        setAgents((prev) =>
          prev.map((a) => (a.id === id ? { ...a, status: normalizeAgentStatus(status) } : a)),
        );
        return true;
      } catch {
        return false;
      }
    },
    [],
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
        setAgentStatus,
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
      addAgent: async () => false,
      updateAgent: async () => false,
      removeAgent: async () => false,
      setAgentStatus: async () => false,
    };
  }
  return context;
}
