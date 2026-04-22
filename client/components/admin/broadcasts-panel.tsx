'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CalendarClock,
  Copy,
  Megaphone,
  MoreVertical,
  Pencil,
  Trash2,
  X,
  Archive,
  ArchiveRestore,
} from 'lucide-react';
import { formatDistanceToNow, intervalToDuration } from 'date-fns';
import { formatBroadcastInstantPkt, parseBackendUtcDate } from '@/lib/tenant-time';

export interface AdminBroadcast {
  id: string;
  title: string;
  message: string;
  startsAt: string;
  endsAt: string;
  occasion: string;
  targetAi: boolean;
  deliveryNotifyAgents: boolean;
  deliveryNotifyCustomersWhatsapp: boolean;
  whatsappTemplateName?: string | null;
  whatsappTemplateLanguage?: string | null;
  whatsappTemplateBodyParameters?: string[] | null;
}

const C = {
  active: '#10b981',
  scheduled: '#f59e0b',
  expired: '#6b7280',
  border: '#e5e7eb',
};

function parseMs(s: string): number {
  const d = parseBackendUtcDate(s) ?? new Date(s);
  const t = d.getTime();
  return Number.isNaN(t) ? NaN : t;
}

function formatSpan(ms: number): string {
  if (ms <= 0) return '0 minutes';
  const d = intervalToDuration({ start: new Date(0), end: new Date(ms) });
  const parts: string[] = [];
  if (d.years) parts.push(`${d.years}y`);
  if (d.months) parts.push(`${d.months}mo`);
  if (d.days) parts.push(`${d.days} day${d.days === 1 ? '' : 's'}`);
  if (d.hours) parts.push(`${d.hours} hour${d.hours === 1 ? '' : 's'}`);
  if (!parts.length && d.minutes) parts.push(`${d.minutes} min`);
  if (!parts.length) return 'under a minute';
  return parts.join(' ');
}

function previewText(msg: string, max = 160): string {
  const t = msg.replace(/\s+/g, ' ').trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

export function BroadcastDeleteModal({
  open,
  title,
  onCancel,
  onConfirm,
  busy,
}: {
  open: boolean;
  title: string;
  onCancel: () => void;
  onConfirm: () => void;
  busy: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="del-broadcast-title"
        className="w-full max-w-md rounded-2xl border bg-white p-6 shadow-xl"
        style={{ borderColor: C.border }}
      >
        <h2 id="del-broadcast-title" className="text-lg font-semibold text-slate-900">
          Delete broadcast
        </h2>
        <p className="mt-3 text-sm text-slate-600">
          Are you sure you want to delete &quot;{title}&quot;?
        </p>
        <p className="mt-2 text-sm text-slate-500">This action cannot be undone.</p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {busy ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function BroadcastWhatsAppModal({
  open,
  count,
  onCancel,
  onConfirm,
  busy,
}: {
  open: boolean;
  count: number;
  onCancel: () => void;
  onConfirm: () => void;
  busy: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-2xl border bg-white p-6 shadow-xl"
        style={{ borderColor: C.border }}
      >
        <h2 className="text-lg font-semibold text-slate-900">Send WhatsApp messages?</h2>
        <p className="mt-3 text-sm text-slate-600">
          You&apos;re about to send this broadcast to{' '}
          <span className="font-semibold text-slate-900">{count.toLocaleString()}</span> customers via
          WhatsApp.
        </p>
        <p className="mt-3 rounded-lg bg-amber-50 border border-amber-200/80 px-3 py-2 text-sm text-amber-900">
          Messages send immediately. Customers inside Meta&apos;s 24-hour session get your title and
          summary as a normal text; everyone else needs an approved template (configured in the form).
          This cannot be undone.
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? 'Sending…' : 'Send now'}
          </button>
        </div>
      </div>
    </div>
  );
}

function BroadcastCard({
  b,
  status,
  now,
  agentCount,
  archived,
  deleting,
  menuOpen,
  onToggleMenu,
  onCloseMenu,
  onEdit,
  onDuplicate,
  onArchive,
  onUnarchive,
  onDeleteClick,
  formatDt,
}: {
  b: AdminBroadcast;
  status: 'active' | 'scheduled' | 'expired';
  now: number;
  agentCount: number;
  archived: boolean;
  deleting: boolean;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onCloseMenu: () => void;
  onEdit: () => void;
  onDuplicate: () => void;
  onArchive: () => void;
  onUnarchive: () => void;
  onDeleteClick: () => void;
  formatDt: (s: string) => string;
}) {
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const fn = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onCloseMenu();
    };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, [menuOpen, onCloseMenu]);

  const start = parseMs(b.startsAt);
  const end = parseMs(b.endsAt);
  const remaining = !Number.isNaN(end) ? end - now : 0;
  const untilStart = !Number.isNaN(start) ? start - now : 0;

  const badge =
    status === 'active' ? (
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-white"
        style={{ backgroundColor: C.active }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-white/90" />
        Active now
      </span>
    ) : status === 'scheduled' ? (
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-white"
        style={{ backgroundColor: C.scheduled }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-white/90" />
        Scheduled
      </span>
    ) : (
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-white"
        style={{ backgroundColor: C.expired }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-white/90" />
        Expired
      </span>
    );

  const scheduleLine = `${formatDt(b.startsAt)} → ${formatDt(b.endsAt)}`;

  const metaLine =
    status === 'active' && remaining > 0 ? (
      <p className="text-xs text-slate-600">
        <span className="font-medium text-slate-800">Remaining:</span> {formatSpan(remaining)}
      </p>
    ) : status === 'scheduled' && untilStart > 0 ? (
      <p className="text-xs text-slate-600">
        <span className="font-medium text-slate-800">Starts in:</span> {formatSpan(untilStart)}
      </p>
    ) : status === 'expired' && !Number.isNaN(end) ? (
      <p className="text-xs text-slate-600">
        <span className="font-medium text-slate-800">Ended:</span>{' '}
        {formatDistanceToNow(parseBackendUtcDate(b.endsAt) ?? new Date(b.endsAt), {
          addSuffix: true,
        })}
      </p>
    ) : null;

  const aiLine = b.targetAi
    ? status === 'expired'
      ? 'AI bot: was active'
      : 'AI bot: included'
    : status === 'expired'
      ? 'AI bot: was off'
      : 'AI bot: not included';

  const agentsLine = b.deliveryNotifyAgents
    ? `Agents Notified: all (${agentCount})`
    : 'Agents: not notified';

  const custLine = b.deliveryNotifyCustomersWhatsapp
    ? b.whatsappTemplateName
      ? `Customers (WhatsApp): template “${b.whatsappTemplateName}” (${b.whatsappTemplateLanguage || '—'}) at creation`
      : 'Customers (WhatsApp): session text at creation (no template name stored)'
    : null;

  return (
    <article
      className="rounded-2xl border bg-white p-4 shadow-sm transition-colors hover:bg-slate-50/80"
      style={{ borderColor: C.border }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">{badge}</div>
        <div className="flex shrink-0 items-center gap-1">
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={onToggleMenu}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              aria-label="More actions"
            >
              <MoreVertical className="h-4 w-4" />
            </button>
            {menuOpen && (
              <div
                className="absolute right-0 top-full z-20 mt-1 w-44 rounded-xl border bg-white py-1 shadow-lg"
                style={{ borderColor: C.border }}
              >
                <button
                  type="button"
                  onClick={() => {
                    onCloseMenu();
                    onEdit();
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                >
                  <Pencil className="h-3.5 w-3.5" /> Edit
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onCloseMenu();
                    onDuplicate();
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                >
                  <Copy className="h-3.5 w-3.5" /> Duplicate
                </button>
                {status === 'expired' && (
                  <>
                    <div className="my-1 border-t" style={{ borderColor: C.border }} />
                    {archived ? (
                      <button
                        type="button"
                        onClick={() => {
                          onCloseMenu();
                          onUnarchive();
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                      >
                        <ArchiveRestore className="h-3.5 w-3.5" /> Unarchive
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          onCloseMenu();
                          onArchive();
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                      >
                        <Archive className="h-3.5 w-3.5" /> Archive
                      </button>
                    )}
                  </>
                )}
                <div className="my-1 border-t" style={{ borderColor: C.border }} />
                <button
                  type="button"
                  onClick={() => {
                    onCloseMenu();
                    onDeleteClick();
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </button>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onDeleteClick}
            disabled={deleting}
            className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
            aria-label="Delete broadcast"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <h3 className="mt-3 text-base font-bold text-slate-900">{b.title}</h3>
      {b.occasion ? (
        <p className="text-xs text-slate-500 mt-0.5">Occasion: {b.occasion}</p>
      ) : null}

      <div className="mt-3 flex items-start gap-2 text-xs text-slate-600">
        <CalendarClock className="h-3.5 w-3.5 shrink-0 mt-0.5 text-slate-400" />
        <div>
          <p className="font-medium text-slate-800">Schedule</p>
          <p>{scheduleLine}</p>
          {metaLine}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-600">
        <span>{aiLine}</span>
        <span className="text-slate-300">·</span>
        <span>{agentsLine}</span>
        {custLine ? (
          <>
            <span className="text-slate-300">·</span>
            <span>{custLine}</span>
          </>
        ) : null}
      </div>

      <div className="mt-3 rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-1">
          {b.targetAi ? 'AI availability preview' : 'Stored text / summary'}
        </p>
        <p className="text-xs text-slate-700 leading-relaxed">&quot;{previewText(b.message)}&quot;</p>
        {b.deliveryNotifyCustomersWhatsapp && b.whatsappTemplateName ? (
          <p className="mt-1.5 text-[10px] text-slate-500">
            WhatsApp template slots:{' '}
            {(b.whatsappTemplateBodyParameters || []).length > 0
              ? (b.whatsappTemplateBodyParameters || []).map((p, i) => `{{${i + 1}}}→${previewText(p, 40)}`).join(' · ')
              : 'none saved'}
          </p>
        ) : null}
      </div>

      {status === 'expired' && !archived && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onArchive}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            style={{ borderColor: C.border }}
          >
            Archive
          </button>
          <button
            type="button"
            onClick={onDeleteClick}
            disabled={deleting}
            className="rounded-lg border border-red-200 bg-red-50/50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      )}
    </article>
  );
}

function LoadingSkeleton() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm overflow-hidden">
      <div className="h-6 w-32 rounded-md bg-slate-200 animate-pulse" />
      <div className="mt-4 h-5 w-3/4 max-w-sm rounded-md bg-slate-200 animate-pulse" />
      <div className="mt-2 h-4 w-full rounded-md bg-slate-100 animate-pulse" />
      <div className="mt-2 h-4 w-5/6 rounded-md bg-slate-100 animate-pulse" />
      <div className="mt-4 h-16 w-full rounded-lg bg-slate-100 animate-pulse" />
    </div>
  );
}

export function BroadcastsPanel({
  broadcasts,
  loading,
  timeZone,
  agentCount,
  archivedIds,
  onArchive,
  onUnarchive,
  onEdit,
  onDuplicate,
  onDeleteClick,
  deletingId,
}: {
  broadcasts: AdminBroadcast[];
  loading: boolean;
  timeZone: string;
  agentCount: number;
  archivedIds: Set<string>;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onEdit: (b: AdminBroadcast) => void;
  onDuplicate: (b: AdminBroadcast) => void;
  onDeleteClick: (b: AdminBroadcast) => void;
  deletingId: string | null;
}) {
  const [now, setNow] = useState(() => Date.now());
  const [menuId, setMenuId] = useState<string | null>(null);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);

  const formatDt = (s: string) => formatBroadcastInstantPkt(s);

  const { active, upcoming, endedVisible, endedArchived } = useMemo(() => {
    const active: AdminBroadcast[] = [];
    const upcoming: AdminBroadcast[] = [];
    const endedVisible: AdminBroadcast[] = [];
    const endedArchived: AdminBroadcast[] = [];

    for (const b of broadcasts) {
      const start = parseMs(b.startsAt);
      const end = parseMs(b.endsAt);
      if (Number.isNaN(start) || Number.isNaN(end)) {
        upcoming.push(b);
        continue;
      }
      if (start <= now && end >= now) {
        active.push(b);
      } else if (start > now) {
        upcoming.push(b);
      } else {
        if (archivedIds.has(b.id)) endedArchived.push(b);
        else endedVisible.push(b);
      }
    }

    upcoming.sort((a, b) => parseMs(a.startsAt) - parseMs(b.startsAt));
    endedVisible.sort((a, b) => parseMs(b.endsAt) - parseMs(a.endsAt));
    endedArchived.sort((a, b) => parseMs(b.endsAt) - parseMs(a.endsAt));
    return { active, upcoming, endedVisible, endedArchived };
  }, [broadcasts, now, archivedIds]);

  const [showArchived, setShowArchived] = useState(false);

  if (loading) {
    return (
      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Active &amp; scheduled broadcasts
        </p>
        <LoadingSkeleton />
        <p className="text-center text-sm text-slate-500">Loading broadcasts…</p>
      </div>
    );
  }

  if (broadcasts.length === 0) {
    return (
      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Active &amp; scheduled broadcasts
        </p>
        <div
          className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-slate-50/50 px-6 py-14 text-center"
          style={{ borderColor: C.border }}
        >
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm border border-slate-200">
            <Megaphone className="h-7 w-7 text-slate-400" strokeWidth={1.5} />
          </div>
          <p className="mt-5 text-sm font-medium text-slate-800">No active or scheduled broadcasts</p>
          <p className="mt-2 max-w-sm text-xs text-slate-500">
            Create your first broadcast using the form above.
          </p>
        </div>
      </div>
    );
  }

  const renderCard = (b: AdminBroadcast, status: 'active' | 'scheduled' | 'expired') => (
    <BroadcastCard
      key={b.id}
      b={b}
      status={status}
      now={now}
      agentCount={agentCount}
      archived={archivedIds.has(b.id)}
      deleting={deletingId === b.id}
      menuOpen={menuId === b.id}
      onToggleMenu={() => setMenuId((id) => (id === b.id ? null : b.id))}
      onCloseMenu={() => setMenuId(null)}
      onEdit={() => onEdit(b)}
      onDuplicate={() => onDuplicate(b)}
      onArchive={() => onArchive(b.id)}
      onUnarchive={() => onUnarchive(b.id)}
      onDeleteClick={() => onDeleteClick(b)}
      formatDt={formatDt}
    />
  );

  return (
    <div className="space-y-6">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        Active &amp; scheduled broadcasts
      </p>

      {active.length > 0 && (
        <div className="space-y-3">
          {active.map((b) => renderCard(b, 'active'))}
        </div>
      )}

      {upcoming.length > 0 && (
        <div className="space-y-3">
          {upcoming.length > 0 && active.length > 0 && (
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">Upcoming</p>
          )}
          {upcoming.map((b) => renderCard(b, 'scheduled'))}
        </div>
      )}

      {(endedVisible.length > 0 || (endedArchived.length > 0 && showArchived)) && (
        <div className="space-y-3">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">Ended</p>
          {endedVisible.map((b) => renderCard(b, 'expired'))}
          {showArchived && endedArchived.map((b) => renderCard(b, 'expired'))}
        </div>
      )}

      {endedArchived.length > 0 && (
        <button
          type="button"
          onClick={() => setShowArchived((v) => !v)}
          className="text-xs font-medium text-primary hover:underline"
        >
          {showArchived
            ? 'Hide archived'
            : `Show archived (${endedArchived.length})`}
        </button>
      )}
    </div>
  );
}
