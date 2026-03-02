'use client';

import { useState } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { UserPlus, Eye, EyeOff } from 'lucide-react';

export default function AdminAgents() {
  const { agents, addAgent } = useAgents();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [revealedIds, setRevealedIds] = useState<Set<string>>(new Set());

  const handleAddAgent = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = email.trim();
    const trimmedName = name.trim();
    const trimmedPassword = password.trim();
    if (!trimmedEmail || !trimmedName || !trimmedPassword) return;
    addAgent(trimmedEmail, trimmedName, trimmedPassword);
    setEmail('');
    setName('');
    setPassword('');
  };

  const toggleReveal = (id: string) => {
    setRevealedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Agents</h1>
        <p className="text-text-secondary mt-1">
          Create agent accounts and set credentials. Agents can edit their picture, name, and change password (updates shown here).
        </p>
      </div>

      <div className="bg-card rounded-xl border border-border shadow-sm p-6 max-w-2xl">
        <h2 className="font-semibold text-text-primary mb-4">Create agent account</h2>
        <p className="text-sm text-text-muted mb-4">
          Set the agent email, name, and initial password. The agent will use these credentials to access the app.
        </p>
        <form onSubmit={handleAddAgent} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="agent@example.com"
              className="w-full px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Agent name"
              className="w-full px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Set initial password"
              className="w-full px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary"
              required
            />
          </div>
          <button
            type="submit"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors"
          >
            <UserPlus className="w-4 h-4" />
            Add agent
          </button>
        </form>
      </div>

      <div className="bg-card rounded-xl border border-border shadow-sm p-6 max-w-2xl">
        <h2 className="font-semibold text-text-primary mb-4">Agent accounts</h2>
        {agents.length === 0 ? (
          <p className="text-text-muted text-sm">No agents yet. Create one above.</p>
        ) : (
          <ul className="space-y-3">
            {agents.map((agent) => (
              <li
                key={agent.id}
                className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 py-4 px-4 rounded-lg bg-panel border border-border"
              >
                <div className="min-w-0">
                  <p className="font-medium text-text-primary">{agent.name}</p>
                  <p className="text-sm text-text-muted">{agent.email}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-text-muted">Password:</span>
                    <code className="text-xs bg-white border border-border rounded px-2 py-0.5 font-mono">
                      {revealedIds.has(agent.id) ? agent.password : '••••••••'}
                    </code>
                    <button
                      type="button"
                      onClick={() => toggleReveal(agent.id)}
                      className="p-1 rounded hover:bg-white text-text-muted"
                      aria-label={revealedIds.has(agent.id) ? 'Hide password' : 'Show password'}
                    >
                      {revealedIds.has(agent.id) ? (
                        <EyeOff className="w-4 h-4" />
                      ) : (
                        <Eye className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
