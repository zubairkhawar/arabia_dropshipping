'use client';

import { useCallback, useEffect, useState } from 'react';
import { Megaphone, FileText } from 'lucide-react';
import { useTenantTimezone } from '@/contexts/TenantTimezoneContext';
import { useAdminRealtime, type AdminRealtimeEvent } from '@/hooks/useAdminRealtime';
import {
  BroadcastTemplatesPanel,
  type WhatsAppTemplate,
} from '@/components/admin/broadcast-templates-panel';
import {
  BroadcastCampaignsPanel,
  type BroadcastCampaign,
} from '@/components/admin/broadcast-campaigns-panel';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://arabia-dropshipping.onrender.com';

type TabKey = 'templates' | 'campaigns';

function authHeaders(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const t = localStorage.getItem('auth_token');
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export default function AdminBroadcastsPage() {
  const { tenantId } = useTenantTimezone();
  const effectiveTenantId = tenantId ?? 1;
  const [tab, setTab] = useState<TabKey>('templates');
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [campaigns, setCampaigns] = useState<BroadcastCampaign[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [campaignsLoading, setCampaignsLoading] = useState(true);

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/broadcasts/whatsapp-message-templates?tenant_id=${effectiveTenantId}`,
        { headers: authHeaders() },
      );
      if (!res.ok) return;
      const data = (await res.json()) as WhatsAppTemplate[];
      setTemplates(data);
    } finally {
      setTemplatesLoading(false);
    }
  }, [effectiveTenantId]);

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/broadcasts/campaigns?tenant_id=${effectiveTenantId}`,
        { headers: authHeaders() },
      );
      if (!res.ok) return;
      const data = (await res.json()) as BroadcastCampaign[];
      setCampaigns(data);
    } finally {
      setCampaignsLoading(false);
    }
  }, [effectiveTenantId]);

  useEffect(() => {
    void loadTemplates();
    void loadCampaigns();
  }, [loadTemplates, loadCampaigns]);

  const onRealtimeEvent = useCallback((ev: AdminRealtimeEvent) => {
    if (ev.type === 'template_status_update') {
      setTemplates((curr) => {
        const idx = curr.findIndex((t) => t.id === ev.template_id);
        if (idx === -1) {
          // Status arrived before list refresh — trigger reload.
          void loadTemplates();
          return curr;
        }
        const next = curr.slice();
        next[idx] = {
          ...next[idx],
          status: ev.status,
          rejection_reason: ev.rejection_reason,
          meta_template_id: ev.meta_template_id,
        };
        return next;
      });
    } else if (ev.type === 'template_deleted') {
      setTemplates((curr) => curr.filter((t) => t.id !== ev.template_id));
    } else if (ev.type === 'campaign_status_update') {
      setCampaigns((curr) => {
        const idx = curr.findIndex((c) => c.id === ev.campaign_id);
        if (idx === -1) {
          void loadCampaigns();
          return curr;
        }
        const next = curr.slice();
        next[idx] = {
          ...next[idx],
          status: ev.status,
          sent_count: ev.sent_count,
          failed_count: ev.failed_count,
          recipient_count: ev.recipient_count,
        };
        return next;
      });
    }
    // recipient_status_update is consumed inside the recipients modal (next reload).
  }, [loadTemplates, loadCampaigns]);

  useAdminRealtime(effectiveTenantId, onRealtimeEvent);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Broadcasts</h1>
        <p className="text-sm text-text-muted">
          Manage WhatsApp message templates (Meta approval) and customer broadcast campaigns.
        </p>
      </div>

      <div className="flex gap-2 border-b border-border">
        <button
          onClick={() => setTab('templates')}
          className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
            tab === 'templates'
              ? 'border-primary text-primary'
              : 'border-transparent text-text-secondary hover:text-text-primary'
          }`}
        >
          <FileText className="h-4 w-4" />
          Templates ({templates.length})
        </button>
        <button
          onClick={() => setTab('campaigns')}
          className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
            tab === 'campaigns'
              ? 'border-primary text-primary'
              : 'border-transparent text-text-secondary hover:text-text-primary'
          }`}
        >
          <Megaphone className="h-4 w-4" />
          Campaigns ({campaigns.length})
        </button>
      </div>

      {tab === 'templates' ? (
        <BroadcastTemplatesPanel
          tenantId={effectiveTenantId}
          templates={templates}
          setTemplates={setTemplates}
          loading={templatesLoading}
          onReload={loadTemplates}
        />
      ) : (
        <BroadcastCampaignsPanel
          tenantId={effectiveTenantId}
          templates={templates}
          campaigns={campaigns}
          setCampaigns={setCampaigns}
          loading={campaignsLoading}
          onReload={loadCampaigns}
        />
      )}
    </div>
  );
}
