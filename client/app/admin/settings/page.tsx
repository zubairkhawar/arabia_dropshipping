'use client';

import { useState, useMemo, useEffect } from 'react';
import { Radio, XCircle, Clock } from 'lucide-react';
import { useOnlineSchedule } from '@/contexts/OnlineScheduleContext';
import { useToast } from '@/contexts/ToastContext';

interface Broadcast {
  id: string;
  title: string;
  message: string;
  startsAt: string;
  endsAt: string;
  occasion: string;
}

function parseBroadcastDate(s: string): number {
  if (!s) return NaN;
  const d = new Date(s);
  return d.getTime();
}

function formatBroadcastDateTime(s: string): string {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export default function AdminSettings() {
  const { schedule, setSchedule } = useOnlineSchedule();
  const { toast } = useToast();
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
    toast('Broadcast added');
  };

  const removeBroadcast = (id: string) => {
    setBroadcasts((prev) => prev.filter((b) => b.id !== id));
  };

  /** End/cancel a broadcast (remove from list so it stops being active). */
  const cancelBroadcast = (id: string) => {
    if (typeof window === 'undefined') return;
    if (confirm('End this broadcast now? The AI will no longer use this message.')) {
      removeBroadcast(id);
      toast('Broadcast ended');
    }
  };

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);
  const activeBroadcast = useMemo(
    () =>
      broadcasts.find((b) => {
        const start = parseBroadcastDate(b.startsAt);
        const end = parseBroadcastDate(b.endsAt);
        return !Number.isNaN(start) && !Number.isNaN(end) && start <= now && end >= now;
      }),
    [broadcasts, now],
  );
  const scheduledBroadcasts = useMemo(
    () =>
      broadcasts.filter((b) => {
        const start = parseBroadcastDate(b.startsAt);
        const end = parseBroadcastDate(b.endsAt);
        if (Number.isNaN(start) || Number.isNaN(end)) return true;
        return end < now || start > now;
      }),
    [broadcasts, now],
  );

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
            <h3 className="font-semibold text-text-primary mb-2 flex items-center gap-2">
              <Clock className="w-4 h-4" />
              Agent online schedule
            </h3>
            <p className="text-xs text-text-secondary mb-4">
              Agents can only appear online during these days and hours. The AI bot uses this to tell
              customers when agents are available. Attendance cannot be marked on days not selected below (e.g. Sunday as holiday).
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-text-primary mb-2">
                  Working days
                </label>
                <div className="flex flex-wrap gap-4">
                  {DAY_LABELS.map((label, dayIndex) => (
                    <label key={dayIndex} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={schedule.workingDays.includes(dayIndex)}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...schedule.workingDays, dayIndex].sort((a, b) => a - b)
                            : schedule.workingDays.filter((d) => d !== dayIndex);
                          setSchedule({ ...schedule, workingDays: next.length > 0 ? next : [1] });
                        }}
                        className="rounded border-border text-primary focus:ring-primary"
                      />
                      <span className="text-sm text-text-primary">{label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-text-primary mb-1">
                    Start time
                  </label>
                  <input
                    type="time"
                    value={schedule.startTime}
                    onChange={(e) => setSchedule({ ...schedule, startTime: e.target.value })}
                    className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-text-primary mb-1">
                    End time
                  </label>
                  <input
                    type="time"
                    value={schedule.endTime}
                    onChange={(e) => setSchedule({ ...schedule, endTime: e.target.value })}
                    className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="border-t border-border pt-6">
            <button
              type="button"
              onClick={() => toast('Settings saved')}
              className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors text-sm"
            >
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

            {activeBroadcast && (
              <div className="bg-status-success/5 border border-status-success/30 rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <Radio className="w-4 h-4 text-status-success shrink-0" />
                  <span className="text-xs font-semibold text-status-success uppercase tracking-wider">
                    Currently live
                  </span>
                </div>
                <p className="font-semibold text-text-primary text-sm">
                  {activeBroadcast.title}
                </p>
                {activeBroadcast.occasion && (
                  <p className="text-[11px] text-text-secondary">
                    Occasion: {activeBroadcast.occasion}
                  </p>
                )}
                <p className="text-xs text-text-secondary">
                  {activeBroadcast.message}
                </p>
                <p className="text-[10px] text-text-muted">
                  {formatBroadcastDateTime(activeBroadcast.startsAt)} →{' '}
                  {formatBroadcastDateTime(activeBroadcast.endsAt)}
                </p>
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => cancelBroadcast(activeBroadcast.id)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-status-error/50 text-status-error text-xs font-medium hover:bg-status-error/10 transition-colors"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                    End broadcast now
                  </button>
                </div>
              </div>
            )}

            {broadcasts.length === 0 ? (
              <p className="text-xs text-text-muted">
                No broadcasts yet. Add one above to tell the AI about agent availability during a
                festival or special event.
              </p>
            ) : (
              <ul className="space-y-2 max-h-64 overflow-y-auto">
                {scheduledBroadcasts.map((b) => {
                  const isPast = parseBroadcastDate(b.endsAt) < now;
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
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold shrink-0 ${
                            isPast ? 'bg-panel text-text-muted' : 'bg-primary/10 text-primary'
                          }`}
                        >
                          {isPast ? 'ENDED' : 'SCHEDULED'}
                        </span>
                      </div>
                      <p className="text-[11px] text-text-secondary line-clamp-2">
                        {b.message}
                      </p>
                      <p className="text-[10px] text-text-muted">
                        {formatBroadcastDateTime(b.startsAt)} → {formatBroadcastDateTime(b.endsAt)}
                      </p>
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={() => cancelBroadcast(b.id)}
                          className="inline-flex items-center gap-1 text-status-error hover:underline text-[10px] font-medium"
                        >
                          <XCircle className="w-3 h-3" />
                          {isPast ? 'Remove' : 'Cancel'}
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
