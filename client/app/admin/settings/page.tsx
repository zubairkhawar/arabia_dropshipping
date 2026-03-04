'use client';

import { useState } from 'react';

interface Broadcast {
  id: string;
  title: string;
  message: string;
  startsAt: string;
  endsAt: string;
  occasion: string;
}

export default function AdminSettings() {
  const [platformName, setPlatformName] = useState('Arabia Dropshipping');
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [title, setTitle] = useState('');
  const [occasion, setOccasion] = useState('');
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [message, setMessage] = useState('');

  const addBroadcast = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim() || !startsAt || !endsAt) return;
    const next: Broadcast = {
      id: `${Date.now()}`,
      title: title.trim(),
      message: message.trim(),
      startsAt,
      endsAt,
      occasion: occasion.trim(),
    };
    setBroadcasts((prev) => [next, ...prev]);
    setTitle('');
    setOccasion('');
    setStartsAt('');
    setEndsAt('');
    setMessage('');
  };

  const removeBroadcast = (id: string) => {
    setBroadcasts((prev) => prev.filter((b) => b.id !== id));
  };

  const nowIso = new Date().toISOString();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
        <p className="text-text-secondary mt-1">
          System configuration and AI behavior controls.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-sidebar rounded-lg p-6 border border-border space-y-6">
          <div>
            <h3 className="font-semibold text-text-primary mb-4">System Configuration</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-text-primary mb-2">
                  Platform Name
                </label>
                <input
                  type="text"
                  value={platformName}
                  onChange={(e) => setPlatformName(e.target.value)}
                  className="w-full px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>
          </div>

          <div className="border-t border-border pt-6">
            <button className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors text-sm">
              Save Changes
            </button>
          </div>
        </div>

        <div className="bg-sidebar rounded-lg p-6 border border-border space-y-5">
          <div>
            <h3 className="font-semibold text-text-primary mb-1">
              AI Broadcast Messages
            </h3>
            <p className="text-xs text-text-secondary">
              Configure temporary festival/occasion messages that the AI bot can use when a
              customer asks for a real agent (for example: Eid, Ramadan, Christmas). The AI
              will read these as \"agent availability notes\" within the active time window.
            </p>
          </div>

          <form onSubmit={addBroadcast} className="space-y-4 bg-card rounded-lg p-4 border border-border">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Title
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Ramadan timings"
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Occasion (optional)
                </label>
                <select
                  value={occasion}
                  onChange={(e) => setOccasion(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="">Custom</option>
                  <option value="Eid">Eid</option>
                  <option value="Ramadan">Ramadan</option>
                  <option value="Christmas">Christmas</option>
                  <option value="National Holiday">National Holiday</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Starts at
                </label>
                <input
                  type="datetime-local"
                  value={startsAt}
                  onChange={(e) => setStartsAt(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Ends at
                </label>
                <input
                  type="datetime-local"
                  value={endsAt}
                  onChange={(e) => setEndsAt(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-primary mb-1">
                Agent availability message for AI
              </label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={4}
                placeholder="Example: Due to Ramadan timings, live agents are only available from 4pm–10pm Gulf Standard Time. I can still help you with most questions right now."
                className="w-full px-3 py-2 border border-border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="mt-1 text-[11px] text-text-muted">
                This text is what the AI bot will use when a customer asks for a real agent while this
                broadcast is active.
              </p>
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                className="bg-primary text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors"
              >
                Add broadcast
              </button>
            </div>
          </form>

          <div className="space-y-3">
            <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
              Active & Scheduled Broadcasts
            </p>
            {broadcasts.length === 0 ? (
              <p className="text-xs text-text-muted">
                No broadcasts yet. Add one above to tell the AI about agent availability during a
                festival or special event.
              </p>
            ) : (
              <ul className="space-y-2 max-h-64 overflow-y-auto">
                {broadcasts.map((b) => {
                  const isActive =
                    b.startsAt && b.endsAt && b.startsAt <= nowIso && b.endsAt >= nowIso;
                  return (
                    <li
                      key={b.id}
                      className="bg-card border border-border rounded-lg p-3 text-xs flex flex-col gap-1"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-semibold text-text-primary truncate">
                            {b.title}
                          </p>
                          {b.occasion && (
                            <p className="text-[11px] text-text-secondary">
                              Occasion: {b.occasion}
                            </p>
                          )}
                        </div>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            isActive
                              ? 'bg-status-success/10 text-status-success'
                              : 'bg-panel text-text-muted'
                          }`}
                        >
                          {isActive ? 'ACTIVE' : 'SCHEDULED'}
                        </span>
                      </div>
                      <p className="text-[11px] text-text-secondary line-clamp-2">
                        {b.message}
                      </p>
                      <p className="text-[10px] text-text-muted">
                        {b.startsAt || '—'} → {b.endsAt || '—'}
                      </p>
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={() => removeBroadcast(b.id)}
                          className="text-[10px] text-status-error hover:underline"
                        >
                          Remove
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
