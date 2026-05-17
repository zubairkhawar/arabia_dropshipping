'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChevronRight, FileUp, Play, Plus, Square, Trash2, Users, X } from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';
import type { WhatsAppTemplate } from '@/components/admin/broadcast-templates-panel';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://arabia-dropshipping.onrender.com';

export interface BroadcastCampaign {
  id: number;
  tenant_id: number;
  title: string;
  template_id: number;
  template_name: string;
  template_language: string;
  recipient_source: 'CSV' | 'AI_CUSTOMERS' | string;
  recipient_count: number;
  sent_count: number;
  failed_count: number;
  status: string;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecipientRow {
  id: number;
  phone: string;
  name: string | null;
  status: string;
  wa_message_id: string | null;
  error_code: string | null;
  error_message: string | null;
  sent_at: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  DRAFT: '#6b7280',
  QUEUED: '#f59e0b',
  SENDING: '#3b82f6',
  COMPLETED: '#10b981',
  FAILED: '#ef4444',
  CANCELED: '#6b7280',
};

function authHeaders(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const t = localStorage.getItem('auth_token');
  return t ? { Authorization: `Bearer ${t}` } : {};
}

interface Props {
  tenantId: number;
  templates: WhatsAppTemplate[];
  campaigns: BroadcastCampaign[];
  setCampaigns: React.Dispatch<React.SetStateAction<BroadcastCampaign[]>>;
  loading: boolean;
  onReload: () => Promise<void>;
}

export function BroadcastCampaignsPanel({
  tenantId,
  templates,
  campaigns,
  setCampaigns,
  loading,
  onReload,
}: Props) {
  const { toast } = useToast();
  const [showBuilder, setShowBuilder] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState<BroadcastCampaign | null>(null);

  const approvedTemplates = templates.filter((t) => t.status === 'APPROVED');

  const startCampaign = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts/campaigns/${id}/start`, {
        method: 'POST',
        headers: authHeaders(),
      });
      if (!res.ok) {
        const body = await res.text();
        toast(`Start failed: ${body || res.status}`);
        return;
      }
      const updated = (await res.json()) as BroadcastCampaign;
      setCampaigns((curr) => curr.map((c) => (c.id === id ? updated : c)));
      toast('Send started — progress will stream live');
    } catch (err) {
      toast(`Start failed: ${String(err)}`);
    }
  };

  const cancelCampaign = async (id: number) => {
    if (!window.confirm('Cancel this campaign? In-flight messages will still be sent.')) return;
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts/campaigns/${id}/cancel`, {
        method: 'POST',
        headers: authHeaders(),
      });
      if (!res.ok) {
        toast(`Cancel failed: ${res.status}`);
        return;
      }
      const updated = (await res.json()) as BroadcastCampaign;
      setCampaigns((curr) => curr.map((c) => (c.id === id ? updated : c)));
    } catch (err) {
      toast(`Cancel failed: ${String(err)}`);
    }
  };

  const deleteCampaign = async (id: number) => {
    if (!window.confirm('Delete this campaign and all its recipients?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts/campaigns/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!res.ok) {
        toast(`Delete failed: ${res.status}`);
        return;
      }
      setCampaigns((curr) => curr.filter((c) => c.id !== id));
    } catch (err) {
      toast(`Delete failed: ${String(err)}`);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text-primary">Broadcast campaigns</h2>
        <div className="flex gap-2">
          <button
            onClick={() => void onReload()}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-panel"
          >
            Reload
          </button>
          <button
            onClick={() => setShowBuilder(true)}
            disabled={approvedTemplates.length === 0}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-white hover:opacity-90 disabled:opacity-50"
            title={approvedTemplates.length === 0 ? 'Need at least one APPROVED template' : undefined}
          >
            <Plus className="h-3.5 w-3.5" />
            New campaign
          </button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-text-muted">Loading…</div>
      ) : campaigns.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-text-muted">
          No campaigns yet.
          {approvedTemplates.length === 0 && (
            <p className="mt-1 text-xs">Create and submit a template first, then come back once Meta approves it.</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {campaigns.map((c) => {
            const color = STATUS_COLORS[c.status] || '#6b7280';
            const progressPct =
              c.recipient_count > 0
                ? Math.round(((c.sent_count + c.failed_count) / c.recipient_count) * 100)
                : 0;
            return (
              <div key={c.id} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-text-primary">{c.title}</span>
                      <span
                        className="rounded-full px-2 py-0.5 text-xs font-medium text-white"
                        style={{ backgroundColor: color }}
                      >
                        {c.status}
                      </span>
                      <span className="text-xs text-text-muted">
                        Template: {c.template_name} · {c.template_language}
                      </span>
                      <span className="text-xs text-text-muted">
                        Source: {c.recipient_source === 'CSV' ? 'CSV upload' : 'AI-bot customers'}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center gap-3 text-xs text-text-secondary">
                      <span>{c.recipient_count} recipients</span>
                      <span className="text-emerald-600">{c.sent_count} sent</span>
                      <span className="text-red-600">{c.failed_count} failed</span>
                    </div>
                    {(c.status === 'SENDING' || c.status === 'COMPLETED' || c.status === 'FAILED') &&
                      c.recipient_count > 0 && (
                        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-border">
                          <div
                            className="h-full bg-primary transition-all"
                            style={{ width: `${progressPct}%` }}
                          />
                        </div>
                      )}
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    <button
                      onClick={() => setSelectedCampaign(c)}
                      className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-panel"
                    >
                      Recipients
                      <ChevronRight className="h-3 w-3" />
                    </button>
                    {(c.status === 'DRAFT' || c.status === 'FAILED') && (
                      <button
                        onClick={() => void startCampaign(c.id)}
                        className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2 py-1 text-xs text-white hover:opacity-90"
                      >
                        <Play className="h-3 w-3" />
                        Start
                      </button>
                    )}
                    {(c.status === 'QUEUED' || c.status === 'SENDING') && (
                      <button
                        onClick={() => void cancelCampaign(c.id)}
                        className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                      >
                        <Square className="h-3 w-3" />
                        Cancel
                      </button>
                    )}
                    {!(c.status === 'QUEUED' || c.status === 'SENDING') && (
                      <button
                        onClick={() => void deleteCampaign(c.id)}
                        className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showBuilder && (
        <CampaignBuilderModal
          tenantId={tenantId}
          approvedTemplates={approvedTemplates}
          onClose={() => setShowBuilder(false)}
          onCreated={(c) => {
            setCampaigns((curr) => [c, ...curr]);
            setShowBuilder(false);
            toast('Campaign created — click Start to begin sending');
          }}
        />
      )}

      {selectedCampaign && (
        <RecipientsModal campaign={selectedCampaign} onClose={() => setSelectedCampaign(null)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Campaign builder
// ---------------------------------------------------------------------------

interface BuilderProps {
  tenantId: number;
  approvedTemplates: WhatsAppTemplate[];
  onClose: () => void;
  onCreated: (c: BroadcastCampaign) => void;
}

function CampaignBuilderModal({ tenantId, approvedTemplates, onClose, onCreated }: BuilderProps) {
  const { toast } = useToast();
  const [title, setTitle] = useState('');
  const [templateId, setTemplateId] = useState<number>(approvedTemplates[0]?.id ?? 0);
  const [source, setSource] = useState<'CSV' | 'AI_CUSTOMERS'>('AI_CUSTOMERS');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [defaultVars, setDefaultVars] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const selectedTpl = approvedTemplates.find((t) => t.id === templateId);
  const placeholderCount = selectedTpl?.body_placeholder_count ?? 0;

  useEffect(() => {
    setDefaultVars(Array.from({ length: placeholderCount }, () => ''));
  }, [placeholderCount]);

  const submit = async () => {
    if (!title.trim()) {
      toast('Title is required');
      return;
    }
    if (!templateId) {
      toast('Pick a template');
      return;
    }
    setSaving(true);
    try {
      let res: Response;
      if (source === 'CSV') {
        if (!csvFile) {
          toast('Choose a CSV file');
          setSaving(false);
          return;
        }
        const fd = new FormData();
        fd.append('tenant_id', String(tenantId));
        fd.append('title', title.trim());
        fd.append('template_id', String(templateId));
        fd.append('file', csvFile);
        res = await fetch(`${API_BASE}/api/broadcasts/campaigns/upload-csv`, {
          method: 'POST',
          headers: authHeaders(),
          body: fd,
        });
      } else {
        res = await fetch(`${API_BASE}/api/broadcasts/campaigns`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tenant_id: tenantId,
            title: title.trim(),
            template_id: templateId,
            recipient_source: 'AI_CUSTOMERS',
            default_variables: defaultVars,
          }),
        });
      }
      if (!res.ok) {
        const body = await res.text();
        toast(`Create failed: ${body || res.status}`);
        return;
      }
      const c = (await res.json()) as BroadcastCampaign;
      onCreated(c);
    } catch (err) {
      toast(`Create failed: ${String(err)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-xl rounded-lg bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="font-semibold text-text-primary">New campaign</h3>
          <button onClick={onClose} className="rounded-md p-1 hover:bg-panel">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3 px-5 py-4">
          <label className="block text-xs font-medium text-text-secondary">
            Title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mt-1 w-full rounded-md border border-border px-2.5 py-1.5 text-sm"
              placeholder="Eid offer for Pakistan customers"
            />
          </label>
          <label className="block text-xs font-medium text-text-secondary">
            Template (approved only)
            <select
              value={templateId}
              onChange={(e) => setTemplateId(Number(e.target.value))}
              className="mt-1 w-full rounded-md border border-border px-2.5 py-1.5 text-sm"
            >
              {approvedTemplates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} · {t.language} · {t.category}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="block text-xs font-medium text-text-secondary">
            <legend>Recipient source</legend>
            <label className="mt-1 flex items-center gap-2">
              <input
                type="radio"
                name="source"
                checked={source === 'AI_CUSTOMERS'}
                onChange={() => setSource('AI_CUSTOMERS')}
              />
              <Users className="h-3.5 w-3.5" />
              All AI-bot customers (existing WhatsApp conversations)
            </label>
            <label className="mt-1 flex items-center gap-2">
              <input type="radio" name="source" checked={source === 'CSV'} onChange={() => setSource('CSV')} />
              <FileUp className="h-3.5 w-3.5" />
              Upload CSV (columns: <code>phone</code>, optional <code>name</code>,{' '}
              <code>var1</code>, <code>var2</code>, …)
            </label>
          </fieldset>
          {source === 'CSV' && (
            <label className="block text-xs font-medium text-text-secondary">
              CSV file
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                className="mt-1 w-full text-xs"
              />
            </label>
          )}
          {source === 'AI_CUSTOMERS' && placeholderCount > 0 && (
            <div className="text-xs font-medium text-text-secondary">
              Default variable values (applied to every recipient)
              <div className="mt-1 space-y-1.5">
                {defaultVars.map((v, i) => (
                  <input
                    key={i}
                    value={v}
                    onChange={(e) => {
                      const next = defaultVars.slice();
                      next[i] = e.target.value;
                      setDefaultVars(next);
                    }}
                    placeholder={`{{${i + 1}}}`}
                    className="w-full rounded-md border border-border px-2.5 py-1.5 text-sm"
                  />
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <button onClick={onClose} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-panel">
            Cancel
          </button>
          <button
            onClick={() => void submit()}
            disabled={saving}
            className="rounded-md bg-primary px-3 py-1.5 text-sm text-white hover:opacity-90 disabled:opacity-50"
          >
            {saving ? 'Creating…' : 'Create draft'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recipients modal
// ---------------------------------------------------------------------------

interface RecipientsProps {
  campaign: BroadcastCampaign;
  onClose: () => void;
}

function RecipientsModal({ campaign, onClose }: RecipientsProps) {
  const [rows, setRows] = useState<RecipientRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/broadcasts/campaigns/${campaign.id}/recipients?limit=200`,
        { headers: authHeaders() },
      );
      if (!res.ok) return;
      const data = (await res.json()) as { total: number; items: RecipientRow[] };
      setRows(data.items);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [campaign.id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex w-full max-w-3xl flex-col rounded-lg bg-card shadow-xl" style={{ maxHeight: '80vh' }}>
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="font-semibold text-text-primary">
            Recipients · {campaign.title} <span className="text-xs text-text-muted">({total})</span>
          </h3>
          <button onClick={onClose} className="rounded-md p-1 hover:bg-panel">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {loading ? (
            <p className="text-sm text-text-muted">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-text-muted">No recipients</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-text-muted">
                <tr>
                  <th className="px-2 py-1.5 text-left">Phone</th>
                  <th className="px-2 py-1.5 text-left">Name</th>
                  <th className="px-2 py-1.5 text-left">Status</th>
                  <th className="px-2 py-1.5 text-left">Error</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="px-2 py-1.5 font-mono">{r.phone}</td>
                    <td className="px-2 py-1.5">{r.name || '—'}</td>
                    <td className="px-2 py-1.5">
                      <span
                        className="rounded-full px-1.5 py-0.5 text-white"
                        style={{ backgroundColor: STATUS_COLORS[r.status] || '#6b7280' }}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-red-600">{r.error_message || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <button onClick={() => void load()} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-panel">
            Reload
          </button>
          <button onClick={onClose} className="rounded-md bg-primary px-3 py-1.5 text-sm text-white hover:opacity-90">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
