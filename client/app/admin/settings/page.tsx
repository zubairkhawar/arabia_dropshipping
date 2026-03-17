"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { Radio, XCircle, Clock, Download, Key, BarChart3, Eye, EyeOff, Copy } from 'lucide-react';
import { useOnlineSchedule } from '@/contexts/OnlineScheduleContext';
import { useToast } from '@/contexts/ToastContext';
import { useAgents } from '@/contexts/AgentsContext';
import { getDayAttendance } from '@/components/agents/activity-bar';
import { buildAllAgentsPdf } from '@/lib/attendance-pdf';

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

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function AdminSettings() {
  const { schedule, setSchedule } = useOnlineSchedule();
  const { toast } = useToast();
  const { agents } = useAgents();
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [reportMonth, setReportMonth] = useState(() => new Date().getMonth() + 1);
  const [reportYear, setReportYear] = useState(() => new Date().getFullYear());
  const [reportDownloading, setReportDownloading] = useState(false);
  const [openaiKeyInput, setOpenaiKeyInput] = useState('');
  const [showOpenaiKey, setShowOpenaiKey] = useState(false);
  const [openaiKeyConfigured, setOpenaiKeyConfigured] = useState(false);
  const [openaiKeySaving, setOpenaiKeySaving] = useState(false);
  const [openaiUsage, setOpenaiUsage] = useState<Record<string, unknown> | null>(null);
  const [openaiUsageLoading, setOpenaiUsageLoading] = useState(false);
  const [openaiUsageError, setOpenaiUsageError] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [occasion, setOccasion] = useState('');
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [message, setMessage] = useState('');

  const TENANT_ID = 1;

  useEffect(() => {
    async function loadBroadcasts() {
      try {
        const res = await fetch(`${API_BASE}/api/broadcasts?tenant_id=${TENANT_ID}`);
        if (!res.ok) return;
        const data = (await res.json()) as {
          id: number;
          tenant_id: number;
          title: string;
          message: string;
          occasion?: string | null;
          starts_at?: string | null;
          ends_at?: string | null;
        }[];
        setBroadcasts(
          data.map((b) => ({
            id: String(b.id),
            title: b.title,
            message: b.message,
            occasion: b.occasion || '',
            startsAt: b.starts_at || '',
            endsAt: b.ends_at || '',
          })),
        );
      } catch {
        // ignore, keep local empty
      }
    }
    loadBroadcasts();
  }, []);

  const addBroadcast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim() || !startsAt || !endsAt) return;
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: TENANT_ID,
          title: title.trim(),
          message: message.trim(),
          occasion: occasion.trim() || null,
          starts_at: startsAt,
          ends_at: endsAt,
        }),
      });
      if (!res.ok) {
        throw new Error('Failed to create broadcast');
      }
      const created = (await res.json()) as {
        id: number;
        title: string;
        message: string;
        occasion?: string | null;
        starts_at?: string | null;
        ends_at?: string | null;
      };
      const next: Broadcast = {
        id: String(created.id),
        title: created.title,
        message: created.message,
        startsAt: created.starts_at || startsAt,
        endsAt: created.ends_at || endsAt,
        occasion: created.occasion || occasion.trim(),
      };
      setBroadcasts((prev) => [next, ...prev]);
      setTitle('');
      setOccasion('');
      setStartsAt('');
      setEndsAt('');
      setMessage('');
      toast("Broadcast added");
    } catch {
      toast("Failed to add broadcast");
    }
  };

  const removeBroadcast = (id: string) => {
    setBroadcasts((prev) => prev.filter((b) => b.id !== id));
  };

  /** End/cancel a broadcast (remove from list so it stops being active). */
  const cancelBroadcast = (id: string) => {
    if (typeof window === "undefined") return;
    if (confirm("End this broadcast now? The AI will no longer use this message.")) {
      // Fire-and-forget delete to backend; we optimistically update UI.
      fetch(`${API_BASE}/api/broadcasts/${id}`, { method: "DELETE" }).catch(() => undefined);
      removeBroadcast(id);
      toast("Broadcast ended");
    }
  };

  const handleDownloadAttendanceReport = async () => {
    if (agents.length === 0) {
      toast("No agents to report");
      return;
    }
    setReportDownloading(true);
    try {
      await buildAllAgentsPdf({
        agents: agents.map((a) => ({ id: a.id, name: a.name, email: a.email })),
        getDayData: (id) => getDayAttendance(id, schedule.workingDays),
        year: reportYear,
        month: reportMonth - 1,
      });
      toast("Report downloaded");
    } catch (e) {
      toast("Failed to generate report");
    } finally {
      setReportDownloading(false);
    }
  };

  const fetchOpenAIConfig = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/ai/openai-config`);
      const data = await r.json();
      setOpenaiKeyConfigured(!!data.key_configured);
    } catch {
      setOpenaiKeyConfigured(false);
    }
  }, []);

  useEffect(() => {
    fetchOpenAIConfig();
  }, [fetchOpenAIConfig]);

  const saveOpenAIKey = async () => {
    setOpenaiKeySaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/ai/openai-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: openaiKeyInput.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          typeof err.detail === "string"
            ? err.detail
            : err.detail?.[0]?.msg || "Failed to save key",
        );
      }
      const data = await res.json();
      setOpenaiKeyConfigured(!!data.key_configured);
      setOpenaiKeyInput('');
      toast("API key saved successfully.");
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "Failed to save key");
    } finally {
      setOpenaiKeySaving(false);
    }
  };

  const fetchOpenAIUsage = async () => {
    setOpenaiUsageLoading(true);
    setOpenaiUsageError(null);
    setOpenaiUsage(null);
    try {
      const res = await fetch(`${API_BASE}/api/ai/openai-usage`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Error ${res.status}`);
      }
      const data = await res.json();
      setOpenaiUsage(data);
    } catch (e: unknown) {
      setOpenaiUsageError(e instanceof Error ? e.message : 'Failed to fetch usage');
    } finally {
      setOpenaiUsageLoading(false);
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
              <div className="pt-0">
                <h4 className="text-sm font-semibold text-text-primary mb-2 flex items-center gap-2">
                  <Key className="w-4 h-4" />
                  OpenAI (GPT) API
                </h4>
                <p className="text-xs text-text-secondary mb-3">
                  The bot is built on OpenAI. Set your API key here; the bot will use it for chat. You can change the key anytime.
                </p>
                <div className="flex flex-wrap gap-2 items-end">
                  <div className="flex-1 min-w-[200px] flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-panel">
                    <input
                      type={showOpenaiKey ? 'text' : 'password'}
                      value={openaiKeyInput}
                      onChange={(e) => setOpenaiKeyInput(e.target.value)}
                      placeholder="sk-..."
                      className="flex-1 min-w-0 bg-transparent border-0 p-0 text-sm focus:outline-none focus:ring-0 font-mono"
                      aria-label="OpenAI API key"
                    />
                    <button
                      type="button"
                      onClick={() => setShowOpenaiKey((v) => !v)}
                      className="p-1 rounded hover:bg-white/80 text-text-muted shrink-0"
                      aria-label={showOpenaiKey ? 'Hide API key' : 'Show API key'}
                    >
                      {showOpenaiKey ? (
                        <EyeOff className="w-3.5 h-3.5" />
                      ) : (
                        <Eye className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (openaiKeyInput && navigator.clipboard?.writeText) {
                          navigator.clipboard.writeText(openaiKeyInput).catch(() => undefined);
                          toast('Copied to clipboard');
                        }
                      }}
                      className="p-1 rounded hover:bg-white/80 text-text-muted shrink-0"
                      aria-label="Copy API key"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={saveOpenAIKey}
                    disabled={openaiKeySaving || !openaiKeyInput.trim()}
                    className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {openaiKeySaving ? 'Saving…' : 'Save key'}
                  </button>
                </div>
                <p className="mt-1.5 text-[11px] text-text-muted">
                  {openaiKeyConfigured ? 'Key configured. Bot will use this key.' : 'No API key set. Add a key so the bot can respond.'}
                </p>

                <div className="mt-4 pt-4 border-t border-border">
                  <h5 className="text-xs font-semibold text-text-primary mb-2 flex items-center gap-1.5">
                    <BarChart3 className="w-3.5 h-3.5" />
                    Usage
                  </h5>
                  <p className="text-[11px] text-text-secondary mb-2">
                    Fetch token and cost usage from OpenAI for the configured key (last 30 days).
                  </p>
                  <button
                    type="button"
                    onClick={fetchOpenAIUsage}
                    disabled={openaiUsageLoading || !openaiKeyConfigured}
                    className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-text-primary hover:bg-panel disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {openaiUsageLoading ? 'Loading…' : 'Fetch usage'}
                  </button>
                  {openaiUsageError && (
                    <p className="mt-2 text-xs text-status-error">{openaiUsageError}</p>
                  )}
                  {openaiUsage != null && (
                    <div className="mt-3 p-3 rounded-lg bg-panel border border-border text-xs overflow-x-auto max-h-48 overflow-y-auto">
                      <pre className="whitespace-pre-wrap break-words text-text-primary">
                        {JSON.stringify(openaiUsage, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
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

      <div className="bg-sidebar rounded-lg p-6 border border-border">
        <h3 className="font-semibold text-text-primary mb-2 flex items-center gap-2">
          <Download className="w-4 h-4" />
          Download Attendance Report
        </h3>
        <p className="text-xs text-text-secondary mb-4">
          Generate a PDF attendance report for all employees for a selected month (logo and layout included).
        </p>
        <div className="flex flex-wrap gap-6 items-end">
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">Month</label>
            <select
              value={reportMonth}
              onChange={(e) => setReportMonth(Number(e.target.value))}
              className="px-3 py-2 border border-border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>{m}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">Year</label>
            <input
              type="number"
              min={2020}
              max={2030}
              value={reportYear}
              onChange={(e) => setReportYear(Number(e.target.value))}
              className="px-3 py-2 border border-border rounded-lg text-sm w-24 focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <button
            type="button"
            disabled={reportDownloading}
            onClick={handleDownloadAttendanceReport}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Download className="w-4 h-4" />
            {reportDownloading ? 'Generating…' : 'Download PDF'}
          </button>
        </div>
      </div>
    </div>
  );
}
