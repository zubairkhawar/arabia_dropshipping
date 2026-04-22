"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Clock, Download, Volume2, Users } from 'lucide-react';
import { useOnlineSchedule } from '@/contexts/OnlineScheduleContext';
import { useTenantTimezone } from '@/contexts/TenantTimezoneContext';
import { useToast } from '@/contexts/ToastContext';
import { useAgents } from '@/contexts/AgentsContext';
import { getDayAttendance, type DayAttendance } from '@/components/agents/activity-bar';
import { buildAllAgentsPdf } from '@/lib/attendance-pdf';
import type { OnlineSchedule } from '@/contexts/OnlineScheduleContext';
import { useSoundAlerts } from '@/contexts/SoundAlertsContext';
import { AgentScheduleSettings } from '@/components/admin/agent-schedule-settings';
import { dateKeyInTimeZone, clockMinutesInTimeZone, parseBackendUtcDate } from '@/lib/tenant-time';
import {
  BroadcastsPanel,
  BroadcastDeleteModal,
  BroadcastWhatsAppModal,
  type AdminBroadcast,
} from '@/components/admin/broadcasts-panel';

const BROADCAST_ARCHIVE_KEY = 'arabia-broadcast-archived-v1';

function toDatetimeLocalValue(iso: string): string {
  const d = parseBackendUtcDate(iso) ?? new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Normalize ``datetime-local`` for API (seconds) and avoid sending ``""`` for datetimes (422). */
function broadcastDateTimeToApi(s: string): string | null {
  const t = (s || '').trim();
  if (!t) return null;
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(t)) return `${t}:00`;
  return t;
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
  const { timeZone, tenantId } = useTenantTimezone();
  const { enabled: soundAlertsEnabled, setEnabled: setSoundAlertsEnabled } = useSoundAlerts();
  const { toast } = useToast();
  const { agents, refreshAgents } = useAgents();
  const [broadcasts, setBroadcasts] = useState<AdminBroadcast[]>([]);
  const [broadcastsLoading, setBroadcastsLoading] = useState(false);
  const [broadcastSubmitting, setBroadcastSubmitting] = useState(false);
  const [deletingBroadcastId, setDeletingBroadcastId] = useState<string | null>(null);
  const [editingBroadcastId, setEditingBroadcastId] = useState<string | null>(null);
  const [deleteModalBroadcast, setDeleteModalBroadcast] = useState<AdminBroadcast | null>(null);
  const [waModalOpen, setWaModalOpen] = useState(false);
  const [waModalCount, setWaModalCount] = useState(0);
  const [waModalSubmitting, setWaModalSubmitting] = useState(false);
  const [whatsappRecipientCount, setWhatsappRecipientCount] = useState<number | null>(null);
  const [archivedBroadcastIds, setArchivedBroadcastIds] = useState<Set<string>>(() => new Set());
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
  const [waTemplates, setWaTemplates] = useState<
    {
      name: string;
      language: string;
      body_placeholder_count: number;
      status?: string | null;
      category?: string | null;
    }[]
  >([]);
  const [waTemplatesLoading, setWaTemplatesLoading] = useState(false);
  const [whatsappTemplateName, setWhatsappTemplateName] = useState('');
  const [whatsappTemplateLanguage, setWhatsappTemplateLanguage] = useState('');
  const [waBodyParams, setWaBodyParams] = useState<string[]>([]);
  const [scheduleDraft, setScheduleDraft] = useState<OnlineSchedule>(schedule);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [maxConcurrentDraft, setMaxConcurrentDraft] = useState(5);
  const [agentMgmtLoading, setAgentMgmtLoading] = useState(false);

  /** Prefer JWT tenant; default 1 matches single-tenant bootstrap. */
  const effectiveTenantId = tenantId ?? 1;

  useEffect(() => {
    setScheduleDraft(schedule);
  }, [schedule]);

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

  useEffect(() => {
    try {
      const raw = localStorage.getItem(BROADCAST_ARCHIVE_KEY);
      if (!raw) return;
      const arr = JSON.parse(raw) as unknown;
      if (Array.isArray(arr)) {
        setArchivedBroadcastIds(new Set(arr.filter((x): x is string => typeof x === 'string')));
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    async function loadWaCount() {
      try {
        const res = await fetch(
          `${API_BASE}/api/broadcasts/whatsapp-recipient-count?tenant_id=${effectiveTenantId}`,
        );
        if (!res.ok) return;
        const j = (await res.json()) as { count?: number };
        if (typeof j.count === 'number') setWhatsappRecipientCount(j.count);
      } catch {
        /* ignore */
      }
    }
    void loadWaCount();
  }, [effectiveTenantId]);

  useEffect(() => {
    if (!deliveryNotifyCustomersWhatsapp) return;
    let cancelled = false;
    (async () => {
      setWaTemplatesLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/broadcasts/whatsapp-templates`);
        if (!res.ok) {
          if (!cancelled) setWaTemplates([]);
          return;
        }
        const data = (await res.json()) as {
          name: string;
          language: string;
          body_placeholder_count?: number;
          status?: string | null;
          category?: string | null;
        }[];
        if (!cancelled) {
          setWaTemplates(
            (Array.isArray(data) ? data : []).map((t) => ({
              name: t.name,
              language: t.language,
              body_placeholder_count:
                typeof t.body_placeholder_count === 'number' ? t.body_placeholder_count : 0,
              status: t.status,
              category: t.category,
            })),
          );
        }
      } catch {
        if (!cancelled) setWaTemplates([]);
      } finally {
        if (!cancelled) setWaTemplatesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [deliveryNotifyCustomersWhatsapp]);

  const waTemplateNameOptions = useMemo(() => {
    const s = new Set<string>();
    for (const t of waTemplates) s.add(t.name);
    return [...s].sort((a, b) => a.localeCompare(b));
  }, [waTemplates]);

  const waLanguagesForSelectedName = useMemo(() => {
    if (!whatsappTemplateName) return [];
    const langs = [
      ...new Set(
        waTemplates.filter((t) => t.name === whatsappTemplateName).map((t) => t.language),
      ),
    ];
    langs.sort((a, b) => a.localeCompare(b));
    return langs;
  }, [waTemplates, whatsappTemplateName]);

  useEffect(() => {
    if (!whatsappTemplateName) return;
    const langs = waLanguagesForSelectedName;
    if (!langs.length) return;
    if (!whatsappTemplateLanguage || !langs.includes(whatsappTemplateLanguage)) {
      setWhatsappTemplateLanguage(langs[0]);
    }
  }, [whatsappTemplateName, waLanguagesForSelectedName, whatsappTemplateLanguage]);

  const selectedWaTemplateMeta = useMemo(
    () =>
      waTemplates.find(
        (t) => t.name === whatsappTemplateName && t.language === whatsappTemplateLanguage,
      ),
    [waTemplates, whatsappTemplateName, whatsappTemplateLanguage],
  );

  useEffect(() => {
    if (waTemplatesLoading) return;
    if (!deliveryNotifyCustomersWhatsapp || !whatsappTemplateName.trim() || !whatsappTemplateLanguage.trim()) {
      return;
    }
    const n = selectedWaTemplateMeta?.body_placeholder_count ?? 0;
    setWaBodyParams((prev) => {
      const next = [...prev];
      if (next.length < n) {
        while (next.length < n) next.push('');
      }
      if (next.length > n) next.length = n;
      return next;
    });
  }, [
    waTemplatesLoading,
    deliveryNotifyCustomersWhatsapp,
    whatsappTemplateName,
    whatsappTemplateLanguage,
    selectedWaTemplateMeta?.body_placeholder_count,
  ]);

  const loadBroadcastsList = useCallback(async () => {
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
        whatsapp_template_name?: string | null;
        whatsapp_template_language?: string | null;
        whatsapp_template_body_parameters?: string[] | null;
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
          whatsappTemplateName: b.whatsapp_template_name ?? undefined,
          whatsappTemplateLanguage: b.whatsapp_template_language ?? undefined,
          whatsappTemplateBodyParameters: Array.isArray(b.whatsapp_template_body_parameters)
            ? b.whatsapp_template_body_parameters.map((x) => String(x))
            : undefined,
        })),
      );
    } catch {
      toast('Failed to load broadcasts');
    } finally {
      setBroadcastsLoading(false);
    }
  }, [effectiveTenantId, toast]);

  useEffect(() => {
    void loadBroadcastsList();
  }, [loadBroadcastsList]);

  const clearBroadcastForm = useCallback(() => {
    setTitle('');
    setOccasion('');
    setStartsAt('');
    setEndsAt('');
    setMessage('');
    setTargetAi(true);
    setDeliveryNotifyAgents(true);
    setDeliveryNotifyCustomersWhatsapp(false);
    setWhatsappTemplateName('');
    setWhatsappTemplateLanguage('');
    setWaBodyParams([]);
    setEditingBroadcastId(null);
  }, []);

  const fillFormFromBroadcast = useCallback((b: AdminBroadcast, duplicate: boolean) => {
    setTitle(duplicate ? `${b.title} (copy)` : b.title);
    setOccasion(b.occasion);
    setStartsAt(b.startsAt ? toDatetimeLocalValue(b.startsAt) : '');
    setEndsAt(b.endsAt ? toDatetimeLocalValue(b.endsAt) : '');
    setMessage(b.message);
    setTargetAi(b.targetAi);
    setDeliveryNotifyAgents(b.deliveryNotifyAgents);
    setDeliveryNotifyCustomersWhatsapp(duplicate ? false : b.deliveryNotifyCustomersWhatsapp);
    if (duplicate || !b.deliveryNotifyCustomersWhatsapp) {
      setWhatsappTemplateName('');
      setWhatsappTemplateLanguage('');
      setWaBodyParams([]);
    } else {
      setWhatsappTemplateName(b.whatsappTemplateName || '');
      setWhatsappTemplateLanguage(b.whatsappTemplateLanguage || '');
      setWaBodyParams([...(b.whatsappTemplateBodyParameters || [])]);
    }
    setEditingBroadcastId(duplicate ? null : b.id);
  }, []);

  const performCreateBroadcast = async () => {
    const startsPayload = broadcastDateTimeToApi(startsAt);
    const endsPayload = broadcastDateTimeToApi(endsAt);
    if (!startsPayload || !endsPayload) {
      throw new Error('Broadcast start and end times are required');
    }
    const res = await fetch(`${API_BASE}/api/broadcasts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: effectiveTenantId,
        title: title.trim(),
        message: (message.trim() || title.trim() || '.').slice(0, 50000),
        occasion: occasion.trim() || null,
        starts_at: startsPayload,
        ends_at: endsPayload,
        target_ai: targetAi,
        delivery_notify_agents: deliveryNotifyAgents,
        delivery_notify_customers_whatsapp: deliveryNotifyCustomersWhatsapp,
        whatsapp_template_name: deliveryNotifyCustomersWhatsapp
          ? whatsappTemplateName.trim() || null
          : null,
        whatsapp_template_language:
          deliveryNotifyCustomersWhatsapp && whatsappTemplateName.trim()
            ? whatsappTemplateLanguage.trim() || 'en_US'
            : null,
        whatsapp_template_body_parameters:
          deliveryNotifyCustomersWhatsapp && whatsappTemplateName.trim() ? waBodyParams : null,
      }),
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const errBody = (await res.json()) as { detail?: unknown };
        if (typeof errBody.detail === 'string') detail = errBody.detail;
        else if (Array.isArray(errBody.detail))
          detail = errBody.detail.map((x: { msg?: string }) => x.msg || '').filter(Boolean).join('; ');
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    await res.json();
    clearBroadcastForm();
    toast('Broadcast added');
    await loadBroadcastsList();
  };

  const addBroadcast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !startsAt || !endsAt) {
      toast('Fill all required broadcast fields');
      return;
    }
    if (targetAi && !message.trim()) {
      toast('When AI bot is selected, fill the agent availability message.');
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

    if (editingBroadcastId) {
      setBroadcastSubmitting(true);
      try {
        const res = await fetch(`${API_BASE}/api/broadcasts/${editingBroadcastId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title.trim(),
            message: (message.trim() || title.trim() || '.').slice(0, 50000),
            occasion: occasion.trim() || null,
            starts_at: broadcastDateTimeToApi(startsAt),
            ends_at: broadcastDateTimeToApi(endsAt),
            target_ai: targetAi,
            delivery_notify_agents: deliveryNotifyAgents,
            delivery_notify_customers_whatsapp: deliveryNotifyCustomersWhatsapp,
            whatsapp_template_name: deliveryNotifyCustomersWhatsapp
              ? whatsappTemplateName.trim() || null
              : null,
            whatsapp_template_language:
              deliveryNotifyCustomersWhatsapp && whatsappTemplateName.trim()
                ? whatsappTemplateLanguage.trim() || 'en_US'
                : null,
            whatsapp_template_body_parameters:
              deliveryNotifyCustomersWhatsapp && whatsappTemplateName.trim() ? waBodyParams : null,
          }),
        });
        if (!res.ok) {
          let detail = 'Failed to update';
          try {
            const errBody = (await res.json()) as { detail?: unknown };
            if (typeof errBody.detail === 'string') detail = errBody.detail;
          } catch {
            /* ignore */
          }
          throw new Error(detail);
        }
        const row = (await res.json()) as {
          id: number;
          title: string;
          message: string;
          occasion?: string | null;
          starts_at?: string | null;
          ends_at?: string | null;
          target_ai?: boolean | null;
          delivery_notify_agents?: boolean | null;
          delivery_notify_customers_whatsapp?: boolean | null;
          whatsapp_template_name?: string | null;
          whatsapp_template_language?: string | null;
          whatsapp_template_body_parameters?: string[] | null;
        };
        const updated: AdminBroadcast = {
          id: String(row.id),
          title: row.title,
          message: row.message,
          occasion: row.occasion || '',
          startsAt: row.starts_at || '',
          endsAt: row.ends_at || '',
          targetAi: row.target_ai !== false,
          deliveryNotifyAgents: !!row.delivery_notify_agents,
          deliveryNotifyCustomersWhatsapp: !!row.delivery_notify_customers_whatsapp,
          whatsappTemplateName: row.whatsapp_template_name ?? undefined,
          whatsappTemplateLanguage: row.whatsapp_template_language ?? undefined,
          whatsappTemplateBodyParameters: Array.isArray(row.whatsapp_template_body_parameters)
            ? row.whatsapp_template_body_parameters.map((x) => String(x))
            : undefined,
        };
        setBroadcasts((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
        clearBroadcastForm();
        toast('Broadcast updated');
        void loadBroadcastsList();
      } catch {
        toast('Failed to update broadcast');
      } finally {
        setBroadcastSubmitting(false);
      }
      return;
    }

    if (deliveryNotifyCustomersWhatsapp) {
      try {
        const res = await fetch(
          `${API_BASE}/api/broadcasts/whatsapp-recipient-count?tenant_id=${effectiveTenantId}`,
        );
        const j = (await res.json()) as { count?: number };
        const c = typeof j.count === 'number' ? j.count : 0;
        setWaModalCount(c);
        setWaModalOpen(true);
      } catch {
        toast('Could not load WhatsApp recipient count');
      }
      return;
    }

    setBroadcastSubmitting(true);
    try {
      await performCreateBroadcast();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to add broadcast');
    } finally {
      setBroadcastSubmitting(false);
    }
  };

  const confirmWhatsAppAndCreate = async () => {
    if (!title.trim() || !startsAt || !endsAt) {
      toast('Fill all required broadcast fields');
      return;
    }
    if (targetAi && !message.trim()) {
      toast('When AI bot is selected, fill the agent availability message.');
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
    setWaModalSubmitting(true);
    try {
      await performCreateBroadcast();
      setWaModalOpen(false);
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to add broadcast');
    } finally {
      setWaModalSubmitting(false);
    }
  };

  const removeBroadcast = (id: string) => {
    setBroadcasts((prev) => prev.filter((b) => b.id !== id));
  };

  const executeDeleteBroadcast = async () => {
    if (!deleteModalBroadcast) return;
    const id = deleteModalBroadcast.id;
    setDeletingBroadcastId(id);
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete');
      removeBroadcast(id);
      setArchivedBroadcastIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        try {
          if (typeof window !== 'undefined') {
            localStorage.setItem(BROADCAST_ARCHIVE_KEY, JSON.stringify([...next]));
          }
        } catch {
          /* ignore */
        }
        return next;
      });
      if (editingBroadcastId === id) clearBroadcastForm();
      toast('Broadcast deleted');
      setDeleteModalBroadcast(null);
    } catch {
      toast('Failed to delete broadcast');
    } finally {
      setDeletingBroadcastId(null);
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
      const fetchAgentAttendance = async (agentId: string): Promise<DayAttendance[]> => {
        const idNum = Number(agentId);
        if (!Number.isFinite(idNum)) {
          return getDayAttendance(agentId, schedule.workingDays, timeZone);
        }
        const url = new URL(`${API_BASE}/api/routing/agents/${idNum}/attendance`);
        url.searchParams.set('tenant_id', String(effectiveTenantId));
        url.searchParams.set('days', '240');
        const res = await fetch(url.toString());
        if (!res.ok) {
          return getDayAttendance(agentId, schedule.workingDays, timeZone);
        }
        const data = (await res.json()) as {
          days: Array<{
            date: string;
            sessions: Array<{ start_at: string; end_at: string | null }>;
          }>;
        };
        const bucket = new Map<
          string,
          { minutes: number; sessions: Array<{ startMinutes: number; endMinutes: number; durationMinutes: number }> }
        >();
        for (const day of data.days || []) {
          const key = String(day.date || '');
          if (!key) continue;
          const row = bucket.get(key) || { minutes: 0, sessions: [] };
          for (const s of day.sessions || []) {
            const st = parseBackendUtcDate(s.start_at);
            if (!st) continue;
            const en = parseBackendUtcDate(s.end_at) ?? new Date();
            const delta = Math.max(0, Math.floor((en.getTime() - st.getTime()) / 60000));
            row.minutes += delta;
            row.sessions.push({
              startMinutes: clockMinutesInTimeZone(st, timeZone),
              endMinutes: clockMinutesInTimeZone(en, timeZone),
              durationMinutes: delta,
            });
          }
          bucket.set(key, row);
        }
        return getDayAttendance(agentId, schedule.workingDays, timeZone).map((d) => {
          const key = dateKeyInTimeZone(d.date, timeZone);
          const real = bucket.get(key);
          if (!real) return { ...d, hoursWorked: 0, sessions: [] };
          return {
            ...d,
            hoursWorked: Math.round((real.minutes / 60) * 100) / 100,
            sessions: real.sessions,
          };
        });
      };

      const attendanceByAgent = new Map<string, DayAttendance[]>();
      await Promise.all(
        agents.map(async (a) => {
          const data = await fetchAgentAttendance(a.id);
          attendanceByAgent.set(a.id, data);
        }),
      );
      await buildAllAgentsPdf({
        agents: agents.map((a) => ({ id: a.id, name: a.name, email: a.email })),
        getDayData: (id) => attendanceByAgent.get(id) ?? getDayAttendance(id, schedule.workingDays, timeZone),
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
          </div>

          <div className="border-t border-border pt-6">
            <h3 className="font-semibold text-text-primary mb-2 flex items-center gap-2">
              <Users className="w-4 h-4" />
              Agent management
            </h3>
            <p className="text-xs text-text-secondary mb-4 max-w-2xl">
              Each agent can only be assigned up to this many open customer threads at once (closed or resolved
              chats do not count). New bot handoffs and transfers are blocked when an agent is at the limit. The
              value applies to every agent; click Save Changes below to persist it.
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
                <p className="text-[11px] text-text-muted mt-1.5">
                  Default is 5. Saved together with agent schedule when you use Save Changes.
                </p>
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
            {editingBroadcastId && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200/80 bg-amber-50/80 px-3 py-2 text-sm text-amber-950">
                <span>
                  Editing broadcast <span className="font-semibold">#{editingBroadcastId}</span> — save with the button below.
                </span>
                <button
                  type="button"
                  onClick={() => clearBroadcastForm()}
                  className="text-xs font-medium text-amber-900 underline hover:no-underline"
                >
                  Cancel edit
                </button>
              </div>
            )}
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
                disabled={!targetAi}
                placeholder="Example: Due to Ramadan timings, live agents are only available from 4pm–10pm Gulf Standard Time. I can still help you with most questions right now."
                className="w-full px-3 py-2 border border-border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <p className="mt-1 text-[11px] text-text-muted">
                Only used when &quot;AI bot&quot; is checked: shown when a customer asks for a human
                during the broadcast window. It is not sent as a WhatsApp template body.
                {!targetAi ? (
                  <span className="block mt-1 text-amber-800/90">
                    AI bot is off — you can leave this empty; the server stores your title as a short
                    summary for lists.
                  </span>
                ) : null}
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
              <label className="flex items-start gap-2 text-sm text-text-primary cursor-pointer group relative">
                <input
                  type="checkbox"
                  checked={deliveryNotifyCustomersWhatsapp}
                  onChange={(e) => {
                    const on = e.target.checked;
                    setDeliveryNotifyCustomersWhatsapp(on);
                    if (!on) {
                      setWhatsappTemplateName('');
                      setWhatsappTemplateLanguage('');
                      setWaBodyParams([]);
                    }
                  }}
                  className="mt-0.5 rounded border-border"
                />
                <span>
                  <span className="font-medium border-b border-dotted border-text-muted/40 cursor-help">
                    Customers (WhatsApp)
                  </span>
                  <span className="block text-[11px] text-text-muted">
                    Send one text per distinct phone that has a WhatsApp thread here (not your
                    full Shopify customer export unless those users are synced and messaged).
                  </span>
                </span>
                <span
                  role="tooltip"
                  className="pointer-events-none invisible group-hover:visible opacity-0 group-hover:opacity-100 transition-opacity absolute left-0 top-full z-30 mt-2 w-[min(100%,280px)] rounded-lg border border-border bg-white p-3 text-[11px] text-text-primary shadow-lg"
                >
                  <span className="font-semibold text-text-primary">
                    {whatsappRecipientCount !== null
                      ? `This will send to ${whatsappRecipientCount.toLocaleString()} customers`
                      : 'Recipient count loading…'}
                  </span>
                  <span className="mt-2 block text-text-secondary leading-relaxed">
                    Only customers who have an existing WhatsApp conversation in this system. Delivery may still
                    require an active session or approved template per Meta rules.
                  </span>
                </span>
              </label>
            </fieldset>

            {deliveryNotifyCustomersWhatsapp && (
              <div className="rounded-lg border border-emerald-200/80 bg-emerald-50/40 p-4 space-y-3">
                <p className="text-xs font-semibold text-text-primary">WhatsApp customer broadcast</p>
                <p className="text-[11px] text-text-secondary leading-relaxed">
                  Recipients who messaged you within Meta&apos;s 24-hour window get a normal text built
                  from the title and summary above. Everyone else is sent the approved template you
                  pick here. In each body slot you can type static text or variables:{' '}
                  <code className="text-[10px] bg-white/80 px-1 rounded">{`{customer_name}`}</code>,{' '}
                  <code className="text-[10px] bg-white/80 px-1 rounded">{`{order_id}`}</code> /{' '}
                  <code className="text-[10px] bg-white/80 px-1 rounded">{`{order_number}`}</code>{' '}
                  (filled per customer from your data).
                </p>
                {waTemplatesLoading ? (
                  <p className="text-xs text-text-muted">Loading templates from Meta…</p>
                ) : waTemplates.length === 0 ? (
                  <p className="text-xs text-amber-900 bg-amber-50/90 border border-amber-200/80 rounded-md px-2 py-2">
                    No approved templates returned. Set{' '}
                    <code className="text-[10px]">META_WHATSAPP_WABA_ID</code> and token on the server
                    and ensure templates are approved in Meta Business Suite.
                  </p>
                ) : (
                  <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-text-primary mb-1">
                          Template name
                        </label>
                        <select
                          value={whatsappTemplateName}
                          onChange={(e) => setWhatsappTemplateName(e.target.value)}
                          className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary"
                        >
                          <option value="">— Optional (session-only text if empty) —</option>
                          {waTemplateNameOptions.map((n) => (
                            <option key={n} value={n}>
                              {n}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-text-primary mb-1">
                          Template language
                        </label>
                        <select
                          value={whatsappTemplateLanguage}
                          onChange={(e) => setWhatsappTemplateLanguage(e.target.value)}
                          disabled={!whatsappTemplateName}
                          className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                        >
                          <option value="">—</option>
                          {waLanguagesForSelectedName.map((lang) => (
                            <option key={lang} value={lang}>
                              {lang}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    {whatsappTemplateName && selectedWaTemplateMeta ? (
                      <div className="space-y-2">
                        <p className="text-[11px] font-medium text-text-primary">
                          Body placeholders (order matches Meta{' '}
                          <code className="text-[10px]">{`{{1}}`}</code>,{' '}
                          <code className="text-[10px]">{`{{2}}`}</code>, …)
                        </p>
                        {Array.from(
                          { length: selectedWaTemplateMeta.body_placeholder_count || 0 },
                          (_, i) => (
                            <div key={i}>
                              <label className="block text-[10px] font-medium text-text-muted mb-0.5">
                                Slot {i + 1}
                              </label>
                              <input
                                type="text"
                                value={waBodyParams[i] ?? ''}
                                onChange={(e) => {
                                  const v = e.target.value;
                                  setWaBodyParams((prev) => {
                                    const next = [...prev];
                                    next[i] = v;
                                    return next;
                                  });
                                }}
                                placeholder={`e.g. {customer_name} or static text`}
                                className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                              />
                            </div>
                          ),
                        )}
                        {(selectedWaTemplateMeta.body_placeholder_count || 0) === 0 ? (
                          <p className="text-[11px] text-text-muted">
                            This template has no named body variables in Meta&apos;s definition, or
                            Meta did not return component text. You can still send it (no body
                            parameters).
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            )}

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={broadcastSubmitting}
                className="bg-primary text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {broadcastSubmitting
                  ? editingBroadcastId
                    ? 'Saving…'
                    : 'Adding…'
                  : editingBroadcastId
                    ? 'Update broadcast'
                    : 'Add broadcast'}
              </button>
            </div>
          </form>

          <div className="max-h-[min(70vh,900px)] overflow-y-auto pr-1 admin-no-scrollbar">
            <BroadcastsPanel
              broadcasts={broadcasts}
              loading={broadcastsLoading}
              timeZone={timeZone}
              agentCount={agents.length}
              archivedIds={archivedBroadcastIds}
              onArchive={(id) => {
                setArchivedBroadcastIds((prev) => {
                  const next = new Set(prev);
                  next.add(id);
                  try {
                    if (typeof window !== 'undefined') {
                      localStorage.setItem(BROADCAST_ARCHIVE_KEY, JSON.stringify([...next]));
                    }
                  } catch {
                    /* ignore */
                  }
                  return next;
                });
              }}
              onUnarchive={(id) => {
                setArchivedBroadcastIds((prev) => {
                  const next = new Set(prev);
                  next.delete(id);
                  try {
                    if (typeof window !== 'undefined') {
                      localStorage.setItem(BROADCAST_ARCHIVE_KEY, JSON.stringify([...next]));
                    }
                  } catch {
                    /* ignore */
                  }
                  return next;
                });
              }}
              onEdit={(b) => fillFormFromBroadcast(b, false)}
              onDuplicate={(b) => fillFormFromBroadcast(b, true)}
              onDeleteClick={(b) => setDeleteModalBroadcast(b)}
              deletingId={deletingBroadcastId}
            />
          </div>

          <BroadcastDeleteModal
            open={deleteModalBroadcast !== null}
            title={deleteModalBroadcast?.title ?? ''}
            busy={deletingBroadcastId !== null}
            onCancel={() => setDeleteModalBroadcast(null)}
            onConfirm={() => void executeDeleteBroadcast()}
          />
          <BroadcastWhatsAppModal
            open={waModalOpen}
            count={waModalCount}
            busy={waModalSubmitting}
            onCancel={() => setWaModalOpen(false)}
            onConfirm={() => void confirmWhatsAppAndCreate()}
          />
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
