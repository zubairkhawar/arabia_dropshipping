'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Send, Trash2, X } from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';
import type { AdminRealtimeEvent } from '@/hooks/useAdminRealtime';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://arabia-dropshipping.onrender.com';

export interface WhatsAppTemplate {
  id: number;
  tenant_id: number;
  name: string;
  language: string;
  category: 'MARKETING' | 'UTILITY' | 'AUTHENTICATION' | string;
  components: Array<{
    type: string;
    format?: string;
    text?: string;
    buttons?: Array<Record<string, unknown>>;
    example?: Record<string, unknown>;
  }>;
  body_placeholder_count: number;
  status: string;
  rejection_reason: string | null;
  meta_template_id: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface Props {
  tenantId: number;
  templates: WhatsAppTemplate[];
  setTemplates: React.Dispatch<React.SetStateAction<WhatsAppTemplate[]>>;
  loading: boolean;
  onReload: () => Promise<void>;
}

const STATUS_COLORS: Record<string, string> = {
  DRAFT: '#6b7280',
  PENDING: '#f59e0b',
  APPROVED: '#10b981',
  REJECTED: '#ef4444',
  PAUSED: '#f59e0b',
  DISABLED: '#6b7280',
};

function authHeaders(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const t = localStorage.getItem('auth_token');
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function BroadcastTemplatesPanel({ tenantId, templates, setTemplates, loading, onReload }: Props) {
  const { toast } = useToast();
  const [showBuilder, setShowBuilder] = useState(false);
  const [submittingId, setSubmittingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const submitTemplate = async (id: number) => {
    setSubmittingId(id);
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts/whatsapp-message-templates/${id}/submit`, {
        method: 'POST',
        headers: authHeaders(),
      });
      if (!res.ok) {
        const body = await res.text();
        toast(`Submit failed: ${body || res.status}`);
        return;
      }
      const updated = (await res.json()) as WhatsAppTemplate;
      setTemplates((curr) => curr.map((t) => (t.id === id ? updated : t)));
      toast('Submitted to Meta — awaiting approval');
    } catch (err) {
      toast(`Submit failed: ${String(err)}`);
    } finally {
      setSubmittingId(null);
    }
  };

  const resyncTemplate = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts/whatsapp-message-templates/${id}/resync`, {
        method: 'POST',
        headers: authHeaders(),
      });
      if (!res.ok) {
        toast(`Resync failed: ${res.status}`);
        return;
      }
      const updated = (await res.json()) as WhatsAppTemplate;
      setTemplates((curr) => curr.map((t) => (t.id === id ? updated : t)));
    } catch (err) {
      toast(`Resync failed: ${String(err)}`);
    }
  };

  const deleteTemplate = async (id: number) => {
    if (!window.confirm('Delete this template? This also removes it from Meta.')) return;
    setDeletingId(id);
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts/whatsapp-message-templates/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!res.ok) {
        toast(`Delete failed: ${res.status}`);
        return;
      }
      setTemplates((curr) => curr.filter((t) => t.id !== id));
      toast('Template deleted');
    } catch (err) {
      toast(`Delete failed: ${String(err)}`);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text-primary">Message templates</h2>
        <div className="flex gap-2">
          <button
            onClick={() => void onReload()}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-panel"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Reload
          </button>
          <button
            onClick={() => setShowBuilder(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-white hover:opacity-90"
          >
            <Plus className="h-3.5 w-3.5" />
            New template
          </button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-text-muted">Loading…</div>
      ) : templates.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-text-muted">
          No templates yet. Create one and submit it to Meta for approval.
        </div>
      ) : (
        <div className="space-y-2">
          {templates.map((t) => {
            const color = STATUS_COLORS[t.status] || '#6b7280';
            const body = t.components.find((c) => c.type?.toUpperCase() === 'BODY')?.text || '';
            return (
              <div key={t.id} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-text-primary">{t.name}</span>
                      <span className="text-xs text-text-muted">·</span>
                      <span className="text-xs text-text-muted">{t.language}</span>
                      <span className="text-xs text-text-muted">·</span>
                      <span className="text-xs text-text-muted">{t.category}</span>
                      <span
                        className="rounded-full px-2 py-0.5 text-xs font-medium text-white"
                        style={{ backgroundColor: color }}
                      >
                        {t.status}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm text-text-secondary line-clamp-2 whitespace-pre-line">{body}</p>
                    {t.status === 'REJECTED' && t.rejection_reason ? (
                      <p className="mt-1.5 text-xs text-red-600">Reason: {t.rejection_reason}</p>
                    ) : null}
                    {t.body_placeholder_count > 0 ? (
                      <p className="mt-1.5 text-xs text-text-muted">
                        {t.body_placeholder_count} body variable{t.body_placeholder_count === 1 ? '' : 's'} (
                        {Array.from({ length: t.body_placeholder_count }, (_, i) => `{{${i + 1}}}`).join(', ')})
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    {(t.status === 'DRAFT' || t.status === 'REJECTED') && (
                      <button
                        onClick={() => void submitTemplate(t.id)}
                        disabled={submittingId === t.id}
                        className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-panel disabled:opacity-50"
                      >
                        <Send className="h-3 w-3" />
                        Submit
                      </button>
                    )}
                    {t.status === 'PENDING' && t.meta_template_id && (
                      <button
                        onClick={() => void resyncTemplate(t.id)}
                        className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-panel"
                        title="Manually refetch from Meta (status normally arrives via WebSocket)"
                      >
                        <RefreshCw className="h-3 w-3" />
                        Resync
                      </button>
                    )}
                    <button
                      onClick={() => void deleteTemplate(t.id)}
                      disabled={deletingId === t.id}
                      className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showBuilder && (
        <TemplateBuilderModal
          tenantId={tenantId}
          onClose={() => setShowBuilder(false)}
          onCreated={(tpl) => {
            setTemplates((curr) => [tpl, ...curr]);
            setShowBuilder(false);
            toast('Template created — submit to Meta when ready');
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Template builder modal
// ---------------------------------------------------------------------------

interface BuilderProps {
  tenantId: number;
  onClose: () => void;
  onCreated: (tpl: WhatsAppTemplate) => void;
}

function TemplateBuilderModal({ tenantId, onClose, onCreated }: BuilderProps) {
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [language, setLanguage] = useState('en');
  const [category, setCategory] = useState<'MARKETING' | 'UTILITY' | 'AUTHENTICATION'>('MARKETING');
  const [headerText, setHeaderText] = useState('');
  const [bodyText, setBodyText] = useState('');
  const [footerText, setFooterText] = useState('');
  const [saving, setSaving] = useState(false);

  const placeholderCount = useMemo(() => {
    const matches = bodyText.match(/\{\{\s*\d+\s*\}\}/g);
    return matches ? matches.length : 0;
  }, [bodyText]);

  const submit = async () => {
    const trimmedName = name.trim().toLowerCase();
    if (!/^[a-z0-9_]+$/.test(trimmedName)) {
      toast('Name must be lowercase a-z, 0-9, underscores only');
      return;
    }
    if (!bodyText.trim()) {
      toast('Body is required');
      return;
    }
    const components: Array<Record<string, unknown>> = [];
    if (headerText.trim()) {
      components.push({ type: 'HEADER', format: 'TEXT', text: headerText.trim() });
    }
    components.push({ type: 'BODY', text: bodyText.trim() });
    if (footerText.trim()) {
      components.push({ type: 'FOOTER', text: footerText.trim() });
    }
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/broadcasts/whatsapp-message-templates`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId,
          name: trimmedName,
          language: language.trim(),
          category,
          components,
        }),
      });
      if (!res.ok) {
        const body = await res.text();
        toast(`Create failed: ${body || res.status}`);
        return;
      }
      const tpl = (await res.json()) as WhatsAppTemplate;
      onCreated(tpl);
    } catch (err) {
      toast(`Create failed: ${String(err)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl rounded-lg bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="font-semibold text-text-primary">New WhatsApp template</h3>
          <button onClick={onClose} className="rounded-md p-1 hover:bg-panel">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3 px-5 py-4">
          <div className="grid grid-cols-3 gap-3">
            <label className="col-span-2 text-xs font-medium text-text-secondary">
              Name (slug)
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="order_shipped_notice"
                className="mt-1 w-full rounded-md border border-border px-2.5 py-1.5 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-text-secondary">
              Language
              <input
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                placeholder="en"
                className="mt-1 w-full rounded-md border border-border px-2.5 py-1.5 text-sm"
              />
            </label>
          </div>
          <label className="block text-xs font-medium text-text-secondary">
            Category
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as typeof category)}
              className="mt-1 w-full rounded-md border border-border px-2.5 py-1.5 text-sm"
            >
              <option value="MARKETING">MARKETING (promotional — opt-in required)</option>
              <option value="UTILITY">UTILITY (order updates, transactional)</option>
              <option value="AUTHENTICATION">AUTHENTICATION (OTP)</option>
            </select>
          </label>
          <label className="block text-xs font-medium text-text-secondary">
            Header (optional, text only)
            <input
              value={headerText}
              onChange={(e) => setHeaderText(e.target.value)}
              maxLength={60}
              className="mt-1 w-full rounded-md border border-border px-2.5 py-1.5 text-sm"
            />
          </label>
          <label className="block text-xs font-medium text-text-secondary">
            Body (use {'{{1}}, {{2}}'} … for variables)
            <textarea
              value={bodyText}
              onChange={(e) => setBodyText(e.target.value)}
              rows={5}
              maxLength={1024}
              className="mt-1 w-full rounded-md border border-border px-2.5 py-1.5 text-sm font-mono"
            />
            {placeholderCount > 0 ? (
              <span className="text-xs text-text-muted">
                {placeholderCount} variable{placeholderCount === 1 ? '' : 's'} detected
              </span>
            ) : null}
          </label>
          <label className="block text-xs font-medium text-text-secondary">
            Footer (optional)
            <input
              value={footerText}
              onChange={(e) => setFooterText(e.target.value)}
              maxLength={60}
              className="mt-1 w-full rounded-md border border-border px-2.5 py-1.5 text-sm"
            />
          </label>
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
            {saving ? 'Saving…' : 'Save as draft'}
          </button>
        </div>
      </div>
    </div>
  );
}
