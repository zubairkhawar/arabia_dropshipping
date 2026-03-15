'use client';

import { useEffect, useMemo, useState } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { UserPlus, MoreVertical, Trash2, Eye, EyeOff, ChevronLeft, ChevronRight, Copy } from 'lucide-react';

export default function AdminAgents() {
  const { agents, addAgent, removeAgent } = useAgents();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [menuAgentId, setMenuAgentId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedId && agents.length > 0) {
      setSelectedId(agents[0].id);
    } else if (selectedId && !agents.find((a) => a.id === selectedId)) {
      setSelectedId(agents[0]?.id ?? null);
    }
  }, [agents, selectedId]);

  const selectedAgent = useMemo(
    () => agents.find((a) => a.id === selectedId) ?? null,
    [agents, selectedId],
  );

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = email.trim();
    const trimmedName = name.trim();
    const trimmedPassword = password.trim();
    if (!trimmedEmail || !trimmedName || !trimmedPassword) return;
    addAgent(trimmedEmail, trimmedName, trimmedPassword);
    setEmail('');
    setName('');
    setPassword('');
    setShowCreateModal(false);
  };

  const handleDelete = (id: string, label: string) => {
    if (!confirm(`Delete agent "${label}" and remove their access to the agent portal?`)) return;
    removeAgent(id);
    if (menuAgentId === id) setMenuAgentId(null);
  };

  const width = listCollapsed ? 64 : 280;

  return (
    <div className="flex h-full">
      <div
        className="flex flex-col h-full border-r border-border bg-white shrink-0 transition-[width] duration-200"
        style={{ width }}
      >
        <div
          className={`flex items-center ${
            listCollapsed ? 'justify-center py-3' : 'justify-between px-3 py-2 h-[56px]'
          } border-b border-border`}
        >
          {listCollapsed ? (
            <button
              type="button"
              onClick={() => setListCollapsed(false)}
              className="p-2 rounded-lg text-text-secondary hover:bg-panel hover:text-text-primary transition-colors"
              aria-label="Expand agents list"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setListCollapsed(true)}
                  className="p-2 rounded-lg text-text-secondary hover:bg-panel hover:text-text-primary transition-colors"
                  aria-label="Collapse agents list"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                    Agents
                  </p>
                  <p className="text-[11px] text-text-secondary">
                    {agents.length} account{agents.length === 1 ? '' : 's'}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center justify-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors"
                aria-label="Add agent"
              >
                <UserPlus className="w-4 h-4" />
                <span>Add</span>
              </button>
            </>
          )}
        </div>

        {!listCollapsed && (
          <div className="flex-1 overflow-y-auto">
            {agents.length === 0 ? (
              <p className="px-4 py-6 text-xs text-text-muted">
                No agents yet. Click “Add” to create an account.
              </p>
            ) : (
              <ul className="p-2 space-y-0.5">
                {agents.map((agent) => {
                  const isActive = agent.id === selectedId;
                  const menuOpen = menuAgentId === agent.id;
                  return (
                    <li
                      key={agent.id}
                      className={`group rounded-lg ${isActive ? 'bg-primary/5' : ''}`}
                    >
                      <div className="flex items-center min-w-0">
                        <button
                          type="button"
                          onClick={() => setSelectedId(agent.id)}
                          className={`flex items-center gap-3 px-3 py-2 rounded-l-lg min-w-0 flex-1 text-left transition-colors ${
                            isActive
                              ? 'text-primary'
                              : 'text-text-secondary hover:bg-panel hover:text-text-primary'
                          }`}
                        >
                          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold flex-shrink-0">
                            {agent.name.charAt(0)}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium truncate">{agent.name}</p>
                            <p className="text-[11px] text-text-muted truncate">
                              {agent.email}
                            </p>
                            <p className="text-[10px] text-text-muted truncate font-mono">
                              ID: {agent.id}
                            </p>
                          </div>
                        </button>
                        <div className="relative pr-1">
                          <button
                            type="button"
                            onClick={() =>
                              setMenuAgentId((current) =>
                                current === agent.id ? null : agent.id,
                              )
                            }
                            className={`p-1.5 rounded-lg transition-colors ${
                              menuOpen
                                ? 'bg-panel text-text-primary'
                                : 'text-text-muted hover:bg-panel hover:text-text-primary opacity-0 group-hover:opacity-100'
                            }`}
                            aria-label="Agent options"
                          >
                            <MoreVertical className="w-4 h-4" />
                          </button>
                          {menuOpen && (
                            <div className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-border bg-card shadow-lg z-20 py-1">
                              <button
                                type="button"
                                onClick={() => handleDelete(agent.id, agent.name)}
                                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-status-error hover:bg-panel text-left"
                              >
                                <Trash2 className="w-4 h-4" />
                                Delete agent
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0 flex flex-col p-6">
        <div className="mb-4">
          <h1 className="text-2xl font-bold text-text-primary">Agent Accounts</h1>
          <p className="text-text-secondary mt-1 text-sm">
            Create, inspect, and revoke access for support agents. Each agent gets their own login
            into the agent portal.
          </p>
        </div>

        {selectedAgent ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-card rounded-xl border border-border shadow-sm p-6 space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary text-lg font-semibold">
                  {selectedAgent.name.charAt(0)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-text-primary">
                    {selectedAgent.name}
                  </p>
                  <p className="text-xs text-text-secondary">Agent login identity</p>
                </div>
              </div>
              <div className="space-y-3 text-sm">
                <div>
                  <p className="text-xs text-text-muted mb-0.5">Agent ID</p>
                  <div className="inline-flex items-center gap-2 px-2 py-1.5 rounded border border-border bg-panel">
                    <code className="text-xs font-mono text-text-primary">{selectedAgent.id}</code>
                    <button
                      type="button"
                      onClick={() => {
                        if (navigator.clipboard?.writeText) {
                          navigator.clipboard.writeText(selectedAgent.id).catch(() => undefined);
                        }
                      }}
                      className="p-1 rounded hover:bg-white text-text-muted"
                      aria-label="Copy agent ID"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <div>
                  <p className="text-xs text-text-muted mb-0.5">Email</p>
                  <p className="text-text-primary break-all">{selectedAgent.email}</p>
                </div>
                <div>
                  <p className="text-xs text-text-muted mb-0.5">Password</p>
                  <div className="flex w-full min-w-0 items-center gap-2 px-3 py-2 rounded border border-border bg-panel">
                    <code className="text-xs font-mono min-w-0 flex-1 truncate">
                      {showPassword ? selectedAgent.password : '••••••••'}
                    </code>
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="p-1 rounded hover:bg-white text-text-muted"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? (
                        <EyeOff className="w-3.5 h-3.5" />
                      ) : (
                        <Eye className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (navigator.clipboard?.writeText) {
                          navigator.clipboard.writeText(selectedAgent.password).catch(() => undefined);
                        }
                      }}
                      className="p-1 rounded hover:bg-white text-text-muted"
                      aria-label="Copy password"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="mt-1 text-[11px] text-text-muted">
                    Share these credentials securely with the agent so they can log into the agent
                    portal.
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-card rounded-xl border border-border shadow-sm p-6 space-y-4">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                Access & Lifecycle
              </p>
              <div className="space-y-3 text-xs">
                <p className="text-text-secondary">
                  Deleting this agent will immediately remove their access to the agent portal. It
                  does not delete historical conversations; those stay attached to their name.
                </p>
                <button
                  type="button"
                  onClick={() => handleDelete(selectedAgent.id, selectedAgent.name)}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-status-error/60 text-status-error hover:bg-status-error/10 text-xs font-medium"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete agent and revoke access
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-sm">
              <p className="text-sm font-medium text-text-primary mb-1">
                No agent selected
              </p>
              <p className="text-xs text-text-secondary mb-3">
                Choose an agent from the agents bar on the left to see their login details and
                access controls.
              </p>
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark"
              >
                <UserPlus className="w-4 h-4" />
                Create first agent
              </button>
            </div>
          </div>
        )}
      </div>

      {showCreateModal && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/40"
          onClick={() => setShowCreateModal(false)}
        >
          <div
            className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4">
              <p className="text-sm font-semibold text-text-primary">Create agent account</p>
              <p className="text-xs text-text-secondary mt-1">
                Set email, name, and initial password. A unique agent ID will be generated by the
                system. Share the credentials with the agent to give them access to the agent portal.
              </p>
            </div>
            <form onSubmit={handleCreate} className="space-y-3 text-sm">
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="agent@example.com"
                  className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Agent name"
                  className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Password
                </label>
                <input
                  type="text"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Set initial password"
                  className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                  required
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary hover:bg-panel"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 px-4 py-1.5 bg-primary text-white rounded-lg text-xs font-medium hover:bg-primary-dark"
                >
                  <UserPlus className="w-4 h-4" />
                  Create agent
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
