"use client";

import { useState, useMemo, useEffect } from "react";
import { Radio, XCircle, Clock, Download, Globe, Volume2, Users } from 'lucide-react';
import { useOnlineSchedule } from '@/contexts/OnlineScheduleContext';
import { useTenantTimezone } from '@/contexts/TenantTimezoneContext';
import { TIMEZONE_GROUPS } from '@/lib/timezone-options';
import { useToast } from '@/contexts/ToastContext';
import { useAgents } from '@/contexts/AgentsContext';
import { getDayAttendance } from '@/components/agents/activity-bar';
import { buildAllAgentsPdf } from '@/lib/attendance-pdf';
import type { OnlineSchedule } from '@/contexts/OnlineScheduleContext';
import { useSoundAlerts } from '@/contexts/SoundAlertsContext';
import { AgentScheduleSettings } from '@/components/admin/agent-schedule-settings';

interface Broadcast {
  id: string;
  title: string;
  message: string;
  startsAt: string;
  endsAt: string;
  occasion: string;
  targetAi: boolean;
  deliveryNotifyAgents: boolean;
  deliveryNotifyCustomersWhatsapp: boolean;
}

function parseBroadcastDate(s: string): number {
  if (!s) return NaN;
  const d = new Date(s);
  return d.getTime();
}

function broadcastTargetSummary(b: Broadcast): string {
  const parts: string[] = [];
  if (b.targetAi) parts.push('AI bot');
  if (b.deliveryNotifyAgents) parts.push('Agent alerts');
  if (b.deliveryNotifyCustomersWhatsapp) parts.push('Customers (WhatsApp)');
  return parts.length ? parts.join(' · ') : '—';
}

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

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://arabia-dropshipping.onrender.com";

export default function AdminSettings() {
  const { schedule, setSchedule } = useOnlineSchedule();
  const { timeZone, setTimeZone, refresh: refreshTenantTimezone, tenantId } = useTenantTimezone();
  const { enabled: soundAlertsEnabled, setEnabled: setSoundAlertsEnabled, requestPlay } = useSoundAlerts();
  const { toast } = useToast();
  const { agents, refreshAgents } = useAgents();
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [broadcastsLoading, setBroadcastsLoading] = useState(false);
  const [broadcastSubmitting, setBroadcastSubmitting] = useState(false);
  const [deletingBroadcastId, setDeletingBroadcastId] = useState<string | null>(null);
  const [reportMonth, setReportMonth] = useState(() => new Date().getMonth() + 1);
  const [reportYear, setReportYear] = useState(() => new Date().getFullYear());
  const [reportDownloading, setReportDownloading] = useState(false);
  const [title, setTitle] = useState('');
  const [occasion, setOccasion] = useState('');
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [message, setMessage] = useState('');
  const [targetAi, setTargetAi] = useState(true);
  const [deliveryNotifyAgents, setDeliveryNotifyAgents] = useState(true);
  const [deliveryNotifyCustomersWhatsapp, setDeliveryNotifyCustomersWhatsapp] = useState(false);
  const [scheduleDraft, setScheduleDraft] = useState<OnlineSchedule>(schedule);
  const [displayTimezoneDraft, setDisplayTimezoneDraft] = useState(timeZone);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [maxConcurrentDraft, setMaxConcurrentDraft] = useState(5);
  const [agentMgmtLoading, setAgentMgmtLoading] = useState(false);
  const [transferSavingId, setTransferSavingId] = useState<string | null>(null);

  /** Prefer JWT tenant; default 1 matches single-tenant bootstrap. */
  const effectiveTenantId = tenantId ?? 1;

  const formatBroadcastDateTime = (s: string): string => {
    if (!s) return '—';
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleString('en-US', {
      timeZone,
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  };

  useEffect(() => {
    setScheduleDraft(schedule);
  }, [schedule]);

  useEffect(() => {
    setDisplayTimezoneDraft(timeZone);
  }, [timeZone]);

  useEffect(() => {
    let cancelled = false;
    async function loadAgentManagement() {
      if (typeof window === 'undefined') return;
      const token = localStorage.getItem('auth_token');
      if (!token) return;
      setAgentMgmtLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/tenants/${effectiveTenantId}/agent-management`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data = (await res.json()) as { max_concurrent_chats_per_agent?: number };
        if (!cancelled && typeof data.max_concurrent_chats_per_agent === 'number') {
          setMaxConcurrentDraft(data.max_concurrent_chats_per_agent);
        }
      } catch {
        // non-fatal
      } finally {
        if (!cancelled) setAgentMgmtLoading(false);
      }
    }
    void loadAgentManagement();
    void refreshAgents();
    return () => {
      cancelled = true;
    };
  }, [refreshAgents, effectiveTenantId]);

  const patchAgentCanTransfer = async (agentId: string, allowed: boolean) => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('auth_token');
    if (!token) {
      toast('Sign in to update agents');
      return;
    }
    setTransferSavingId(agentId);
    try {
      const res = await fetch(`${API_BASE}/api/agents/${agentId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ can_transfer_conversations: allowed }),
      });
      if (!res.ok) {
        throw new Error('Failed to update');
      }
      toast(allowed ? 'Agent can transfer chats' : 'Transfer disabled for agent');
      await refreshAgents();
    } catch {
      toast('Failed to update transfer permission');
    } finally {
      setTransferSavingId(null);
    }
  };

  useEffect(() => {
    async function loadBroadcasts() {
      setBroadcastsLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/broadcasts?tenant_id=${effectiveTenantId}`);
        if (!res.ok) throw new Error('Failed to fetch broadcasts');
        const data = (await res.json()) as {
          id: number;
          tenant_id: number;
          title: string;
          message: string;
          occasion?: string | null;
          starts_at?: string | null;
          ends_at?: string | null;
          target_ai?: boolean | null;
          delivery_notify_agents?: boolean | null;
          delivery_notify_customers_whatsapp?: boolean | null;
        }[];
        setBroadcasts(
          data.map((b) => ({
            id: String(b.id),
            title: b.title,
            message: b.message,
            occasion: b.occasion || '',
            startsAt: b.starts_at || '',
            endsAt: b.ends_at || '',
            targetAi: b.target_ai !== false,
            deliveryNotifyAgents: !!b.delivery_notify_agents,
            deliveryNotifyCustomersWhatsapp: !!b.delivery_notify_customers_whatsapp,
          })),
        );
      } catch {
        toast('Failed to load broadcasts');
      } finally {
        setBroadcastsLoading(false);
      }
    }
    void loadBroadcasts();
  }, [toast, effectiveTenantId]);

  const addBroadcast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim() || !startsAt || !endsAt) {
      toast('Fill all required broadcast fields');
      return;
    }
    if (!targetAi && !deliveryNotifyAgents && !deliveryNotifyCustomersWhatsapp) {
      toast('Choose at least one target: AI bot, agents, and/or customers (WhatsApp)');
      return;
    }
    if (new Date(endsAt).getTime() <= new Date(startsAt).getTime()) {
      toast('Broadcast end time must be after start time');
      return;
    }
    setBroadcastSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: effectiveTenantId,
          title: title.trim(),
          message: message.trim(),
          occasion: occasion.trim() || null,
          starts_at: startsAt,
          ends_at: endsAt,
          target_ai: targetAi,
          delivery_notify_agents: deliveryNotifyAgents,
          delivery_notify_customers_whatsapp: deliveryNotifyCustomersWhatsapp,
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
        target_ai?: boolean | null;
        delivery_notify_agents?: boolean | null;
        delivery_notify_customers_whatsapp?: boolean | null;
      };
      const next: Broadcast = {
        id: String(created.id),
        title: created.title,
        message: created.message,
        startsAt: created.starts_at || startsAt,
        endsAt: created.ends_at || endsAt,
        occasion: created.occasion || occasion.trim(),
        targetAi: created.target_ai !== false,
        deliveryNotifyAgents: !!created.delivery_notify_agents,
        deliveryNotifyCustomersWhatsapp: !!created.delivery_notify_customers_whatsapp,
      };
      setBroadcasts((prev) => [next, ...prev]);
      setTitle('');
      setOccasion('');
      setStartsAt('');
      setEndsAt('');
      setMessage('');
      setTargetAi(true);
      setDeliveryNotifyAgents(false);
      setDeliveryNotifyCustomersWhatsapp(false);
      toast("Broadcast added");
    } catch {
      toast("Failed to add broadcast");
    } finally {
      setBroadcastSubmitting(false);
    }
  };

  const removeBroadcast = (id: string) => {
    setBroadcasts((prev) => prev.filter((b) => b.id !== id));
  };

  /** End/cancel a broadcast (remove from list so it stops being active). */
  const cancelBroadcast = async (id: string) => {
    if (typeof window === "undefined") return;
    if (confirm("End this broadcast now? The AI will no longer use this message.")) {
      setDeletingBroadcastId(id);
      try {
        const res = await fetch(`${API_BASE}/api/broadcasts/${id}`, { method: "DELETE" });
        if (!res.ok) throw new Error('Failed to delete');
        removeBroadcast(id);
        toast("Broadcast ended");
      } catch {
        toast("Failed to end broadcast");
      } finally {
        setDeletingBroadcastId(null);
      }
    }
  };

  const saveAllSystemSettings = async () => {
    if (typeof window === 'undefined') return;
    if (scheduleDraft.workingDays.length === 0) {
      toast('Select at least one working day');
      return;
    }
    if (!scheduleDraft.startTime || !scheduleDraft.endTime) {
      toast('Set both start and end time');
      return;
    }
    if (scheduleDraft.endTime <= scheduleDraft.startTime) {
      toast('End time must be later than start time');
      return;
    }
    const token = localStorage.getItem('auth_token');
    if (!token) {
      toast('Sign in to save settings');
      return;
    }
    setSettingsSaving(true);
    try {
      const tzRes = await fetch(`${API_BASE}/api/tenants/${effectiveTenantId}/display-timezone`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ display_timezone: displayTimezoneDraft }),
      });
      if (!tzRes.ok) {
        const err = await tzRes.json().catch(() => ({}));
        const msg =
          typeof err.detail === 'string'
            ? err.detail
            : Array.isArray(err.detail)
              ? err.detail[0]?.msg
              : 'Failed to save timezone';
        throw new Error(msg || 'Failed to save timezone');
      }

      const schedRes = await fetch(`${API_BASE}/api/tenants/${effectiveTenantId}/schedule`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          working_days: scheduleDraft.workingDays,
          start_time: scheduleDraft.startTime,
          end_time: scheduleDraft.endTime,
        }),
      });
      if (!schedRes.ok) {
        throw new Error('Failed to save agent schedule');
      }

      const cap = Math.min(100, Math.max(1, parseInt(String(maxConcurrentDraft), 10) || 5));
      const amRes = await fetch(`${API_BASE}/api/tenants/${effectiveTenantId}/agent-management`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ max_concurrent_chats_per_agent: cap }),
      });
      if (!amRes.ok) {
        const err = await amRes.json().catch(() => ({}));
        const msg =
          typeof (err as { detail?: string }).detail === 'string'
            ? (err as { detail: string }).detail
            : 'Failed to save agent capacity';
        throw new Error(msg);
      }
      const amData = (await amRes.json()) as { max_concurrent_chats_per_agent?: number };
      if (typeof amData.max_concurrent_chats_per_agent === 'number') {
        setMaxConcurrentDraft(amData.max_concurrent_chats_per_agent);
      }

      setTimeZone(displayTimezoneDraft);
      await refreshTenantTimezone();
      setSchedule(scheduleDraft);
      await refreshAgents();
      toast('Changes saved successfully');
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : 'Failed to save settings');
    } finally {
      setSettingsSaving(false);
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
        timeZone,
      });
      toast("Report downloaded");
    } catch (e) {
      toast("Failed to generate report");
    } finally {
      setReportDownloading(false);
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
          </div>

          <div className="border-t border-border pt-6">
            <h3 className="font-semibold text-text-primary mb-2 flex items-center gap-2">
              <Volume2 className="w-4 h-4" />
              Sound alerts
            </h3>
            <p className="text-xs text-text-secondary mb-3">
              Plays in this browser when agents receive new customer messages, notifications, team @mentions, or DMs.
              At most one sound every 3 seconds to avoid spam.
            </p>
            <div className="flex items-center justify-between gap-4 max-w-xl py-2 px-3 rounded-lg border border-border bg-panel">
              <span className="text-sm text-text-primary">Play sound on new message / notification</span>
              <button
                type="button"
                role="switch"
                aria-checked={soundAlertsEnabled}
                onClick={() => {
                  setSoundAlertsEnabled(!soundAlertsEnabled);
                  toast(soundAlertsEnabled ? 'Sound alerts off' : 'Sound alerts on');
                }}
                className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
                  soundAlertsEnabled ? 'bg-primary' : 'bg-border'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow transition ${
                    soundAlertsEnabled ? 'translate-x-5' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </div>
            <p className="mt-4 text-[10px] text-text-muted max-w-2xl">
              Multiple events within 3 seconds only trigger one sound. Sustained activity (e.g. several messages
              spread over 10 seconds) can play once per 3 seconds each.
            </p>
            <div className="mt-4 max-w-xl">
              <button
                type="button"
                onClick={() => {
                  requestPlay('customer_message');
                  toast(
                    soundAlertsEnabled
                      ? 'Played test chime (if audio is blocked, click again after interacting with the page).'
                      : 'Turn sound alerts on above to hear the test chime.',
                  );
                }}
                className="text-sm font-medium text-primary hover:underline"
              >
                Test chime (customer message sound)
              </button>
              <p className="mt-1 text-[10px] text-text-muted">
                Uses the same path as live alerts (respects the master toggle and the 3 second debounce).
              </p>
            </div>
          </div>

          <div className="border-t border-border pt-6">
            <h3 className="font-semibold text-text-primary mb-2 flex items-center gap-2">
              <Users className="w-4 h-4" />
              Agent management
            </h3>
            <p className="text-xs text-text-secondary mb-4 max-w-2xl">
              Cap how many active customer conversations each agent can hold at once (routing and transfers respect
              this). Choose which agents may transfer chats to teammates; changes apply on save or immediately for
              transfer toggles.
            </p>
            <div className="space-y-4 max-w-2xl">
              <div>
                <label htmlFor="max-concurrent-chats" className="block text-xs font-medium text-text-primary mb-1">
                  Max concurrent chats per agent
                </label>
                <input
                  id="max-concurrent-chats"
                  type="number"
                  min={1}
                  max={100}
                  value={maxConcurrentDraft}
                  disabled={agentMgmtLoading}
                  onChange={(e) => setMaxConcurrentDraft(parseInt(e.target.value, 10) || 1)}
                  className="w-32 px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                />
                <p className="mt-1 text-[10px] text-text-muted">
                  Saved with <span className="font-medium">Save Changes</span> below (1–100). Updates every agent in
                  this tenant.
                </p>
              </div>
              <div>
                <p className="text-xs font-medium text-text-primary mb-2">Can transfer conversations</p>
                {agents.length === 0 ? (
                  <p className="text-xs text-text-secondary">No agents yet. Add agents from the Agents screen.</p>
                ) : (
                  <div className="border border-border rounded-lg overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-panel text-text-muted font-medium">
                        <tr>
                          <th className="py-2 px-3 border-b border-border">Agent</th>
                          <th className="py-2 px-3 border-b border-border w-32">Transfer</th>
                        </tr>
                      </thead>
                      <tbody className="text-text-primary">
                        {agents.map((a) => (
                          <tr key={a.id} className="border-b border-border/80 last:border-0">
                            <td className="py-2 px-3">
                              <div className="font-medium">{a.name}</div>
                              <div className="text-[10px] text-text-muted">{a.email}</div>
                            </td>
                            <td className="py-2 px-3">
                              <button
                                type="button"
                                role="switch"
                                aria-checked={a.canTransferConversations}
                                disabled={transferSavingId === a.id}
                                onClick={() => void patchAgentCanTransfer(a.id, !a.canTransferConversations)}
                                className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed ${
                                  a.canTransferConversations ? 'bg-primary' : 'bg-border'
                                }`}
                              >
                                <span
                                  className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow transition ${
                                    a.canTransferConversations ? 'translate-x-5' : 'translate-x-0.5'
                                  }`}
                                />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="border-t border-border pt-6">
            <h3 className="font-semibold text-text-primary mb-2 flex items-center gap-2">
              <Globe className="w-4 h-4" />
              Display timezone
            </h3>
            <p className="text-xs text-text-secondary mb-4">
              All agents and admins see message times, conversation lists, notifications, and attendance labels in
              this timezone. Data stays stored in UTC; only display changes when you update this.
            </p>
            <div className="space-y-3 max-w-xl">
              <div>
                <label htmlFor="tenant-timezone" className="block text-xs font-medium text-text-primary mb-1">
                  Timezone
                </label>
                <select
                  id="tenant-timezone"
                  value={displayTimezoneDraft}
                  onChange={(e) => setDisplayTimezoneDraft(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  {TIMEZONE_GROUPS.map((g) => (
                    <optgroup key={g.region} label={g.region}>
                      {g.zones.map((z) => (
                        <option key={z.id} value={z.id}>
                          {z.label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="border-t border-border pt-6">
            <h3 className="font-semibold text-text-primary mb-1 flex items-center gap-2">
              <Clock className="w-4 h-4" />
              Agent online schedule
            </h3>
            <p className="text-xs text-text-secondary mb-5 max-w-2xl">
              Agents can only appear online during these days and hours. The AI uses this for customer-facing
              availability. Attendance cannot be marked on days that are off.
            </p>
            <AgentScheduleSettings value={scheduleDraft} onChange={setScheduleDraft} />
          </div>

          <div className="border-t border-border pt-6">
            <button
              type="button"
              onClick={() => void saveAllSystemSettings()}
              disabled={settingsSaving}
              className="bg-primary text-white px-6 py-2 rounded-lg hover:bg-primary-dark transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {settingsSaving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </div>

        <div className="bg-sidebar rounded-lg p-6 border border-border space-y-5">
          <div>
            <h3 className="font-semibold text-text-primary mb-1">
              AI Broadcast Messages
            </h3>
            <p className="text-xs text-text-secondary">
              Configure temporary festival/occasion messages. You can feed them to the AI as
              agent-availability notes, notify your team, and/or message customers on WhatsApp
              when you add a broadcast (customers reached are those already in this system with
              a WhatsApp conversation).
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
                When &quot;AI bot&quot; is selected below, this text is used when a customer asks
                for a real agent while the broadcast window is active.
              </p>
            </div>

            <fieldset className="space-y-2 rounded-lg border border-border bg-panel/30 p-3">
              <legend className="px-1 text-xs font-medium text-text-primary">
                Also apply / send when you add this broadcast
              </legend>
              <p className="text-[11px] text-text-muted pb-1">
                Choose any combination. Agent alerts and WhatsApp sends run once when you click
                Add broadcast. WhatsApp uses your Meta Cloud API; delivery may fail outside
                Meta&apos;s messaging rules (e.g. 24-hour session or approved templates).
              </p>
              <label className="flex items-start gap-2 text-sm text-text-primary cursor-pointer">
                <input
                  type="checkbox"
                  checked={targetAi}
                  onChange={(e) => setTargetAi(e.target.checked)}
                  className="mt-0.5 rounded border-border"
                />
                <span>
                  <span className="font-medium">AI bot</span>
                  <span className="block text-[11px] text-text-muted">
                    Include this message in AI &quot;agent availability&quot; context for the
                    scheduled window.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm text-text-primary cursor-pointer">
                <input
                  type="checkbox"
                  checked={deliveryNotifyAgents}
                  onChange={(e) => setDeliveryNotifyAgents(e.target.checked)}
                  className="mt-0.5 rounded border-border"
                />
                <span>
                  <span className="font-medium">Agents (notifications)</span>
                  <span className="block text-[11px] text-text-muted">
                    Create an in-app notification for every agent on this tenant.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm text-text-primary cursor-pointer">
                <input
                  type="checkbox"
                  checked={deliveryNotifyCustomersWhatsapp}
                  onChange={(e) => setDeliveryNotifyCustomersWhatsapp(e.target.checked)}
                  className="mt-0.5 rounded border-border"
                />
                <span>
                  <span className="font-medium">Customers (WhatsApp)</span>
                  <span className="block text-[11px] text-text-muted">
                    Send one text per distinct phone that has a WhatsApp thread here (not your
                    full Shopify customer export unless those users are synced and messaged).
                  </span>
                </span>
              </label>
            </fieldset>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={broadcastSubmitting}
                className="bg-primary text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {broadcastSubmitting ? 'Adding...' : 'Add broadcast'}
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
                <p className="text-[10px] text-text-secondary">
                  Targets: {broadcastTargetSummary(activeBroadcast)}
                </p>
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => void cancelBroadcast(activeBroadcast.id)}
                    disabled={deletingBroadcastId === activeBroadcast.id}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-status-error/50 text-status-error text-xs font-medium hover:bg-status-error/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                    {deletingBroadcastId === activeBroadcast.id ? 'Ending...' : 'End broadcast now'}
                  </button>
                </div>
              </div>
            )}

            {broadcastsLoading ? (
              <p className="text-xs text-text-muted">Loading broadcasts...</p>
            ) : broadcasts.length === 0 ? (
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
                      <p className="text-[10px] text-text-secondary">
                        Targets: {broadcastTargetSummary(b)}
                      </p>
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={() => void cancelBroadcast(b.id)}
                          disabled={deletingBroadcastId === b.id}
                          className="inline-flex items-center gap-1 text-status-error hover:underline text-[10px] font-medium disabled:opacity-50 disabled:no-underline"
                        >
                          <XCircle className="w-3 h-3" />
                          {deletingBroadcastId === b.id ? 'Removing...' : isPast ? 'Remove' : 'Cancel'}
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
