'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useToast } from '@/contexts/ToastContext';

type SourceType = 'file' | 'url' | 'api';

interface KnowledgeSource {
  id: string;
  name: string;
  type: SourceType;
  status: 'indexing' | 'ready' | 'error';
  chunks: number;
  lastUpdated: string;
  lastError?: string;
  url?: string | null;
  authType?: string;
  refreshHours?: number;
  headerKeys?: string[];
  schemaNotes?: string;
}

interface KnowledgeSourceApi {
  id: number;
  tenant_id: number;
  name: string;
  type: SourceType;
  url: string | null;
  status: 'indexing' | 'ready' | 'error';
  chunk_count: number;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const DEFAULT_TENANT_ID = 1;

export default function AdminKnowledgeBase() {
  const { toast } = useToast();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [fileName, setFileName] = useState('');
  const [url, setUrl] = useState('');
  const [apiName, setApiName] = useState('');
  const [apiUrl, setApiUrl] = useState('');
  const [authType, setAuthType] = useState<'none' | 'api_key' | 'bearer'>('none');
  const [apiKey, setApiKey] = useState('');
  const [headers, setHeaders] = useState('');
  const [refreshInterval, setRefreshInterval] = useState('24');
  const [schemaNotes, setSchemaNotes] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmittingFile, setIsSubmittingFile] = useState(false);
  const [isSubmittingUrl, setIsSubmittingUrl] = useState(false);
  const [isSubmittingApi, setIsSubmittingApi] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [reindexingId, setReindexingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const mapSource = useCallback((s: KnowledgeSourceApi): KnowledgeSource => {
    const updated = s.updated_at || s.created_at;
    return {
      id: String(s.id),
      name: s.name,
      type: s.type,
      status: s.status === 'ready' ? 'ready' : s.status === 'error' ? 'error' : 'indexing',
      chunks: s.chunk_count,
      lastUpdated: updated ? new Date(updated).toLocaleString() : '-',
      lastError: typeof s.metadata?.last_error === 'string' ? s.metadata.last_error : undefined,
      url: s.url,
      authType: typeof s.metadata?.auth_type === 'string' ? s.metadata.auth_type : undefined,
      refreshHours:
        typeof s.metadata?.refresh_interval_hours === 'number'
          ? s.metadata.refresh_interval_hours
          : undefined,
      headerKeys:
        s.metadata?.headers && typeof s.metadata.headers === 'object'
          ? Object.keys(s.metadata.headers as Record<string, unknown>)
          : [],
      schemaNotes:
        typeof s.metadata?.schema_notes === 'string' ? s.metadata.schema_notes : undefined,
    };
  }, []);

  const fetchSources = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/knowledge/sources?tenant_id=${DEFAULT_TENANT_ID}`,
        { method: 'GET' },
      );
      if (!res.ok) {
        toast('Failed to load knowledge sources');
        return;
      }
      const data = (await res.json()) as KnowledgeSourceApi[];
      setSources(data.map(mapSource));
    } catch {
      toast('Failed to load knowledge sources');
    } finally {
      setIsLoading(false);
    }
  }, [mapSource, toast]);

  useEffect(() => {
    void fetchSources();
  }, [fetchSources]);

  const createSource = useCallback(
    async (payload: {
      name: string;
      type: SourceType;
      url?: string;
      metadata?: Record<string, unknown>;
    }) => {
      const res = await fetch(`${API_BASE_URL}/api/knowledge/sources`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: DEFAULT_TENANT_ID,
          name: payload.name,
          type: payload.type,
          url: payload.url ?? null,
          metadata: payload.metadata ?? {},
        }),
      });
      if (!res.ok) {
        throw new Error('create_failed');
      }
      const created = (await res.json()) as KnowledgeSourceApi;
      setSources((prev) => [mapSource(created), ...prev]);
    },
    [mapSource],
  );

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
  };

  const handleFileAdd = async () => {
    const trimmed = fileName.trim();
    if (!trimmed) {
      toast('Please choose a file');
      return;
    }
    setIsSubmittingFile(true);
    try {
      await createSource({
        name: trimmed,
        type: 'file',
        metadata: {
          filename: trimmed,
        },
      });
      toast('File source added');
      setFileName('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch {
      toast('Failed to add file source');
    } finally {
      setIsSubmittingFile(false);
    }
  };

  const handleUrlAdd = async () => {
    const trimmed = url.trim();
    if (!trimmed) {
      toast('Please enter a URL');
      return;
    }
    setIsSubmittingUrl(true);
    try {
      await createSource({
        name: trimmed,
        type: 'url',
        url: trimmed,
        metadata: { seed_url: trimmed },
      });
      toast('URL source added');
      setUrl('');
    } catch {
      toast('Failed to add URL source');
    } finally {
      setIsSubmittingUrl(false);
    }
  };

  const handleApiAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = apiName.trim();
    const trimmedUrl = apiUrl.trim();
    if (!trimmedName || !trimmedUrl) {
      toast('API name and base URL are required');
      return;
    }
    let parsedHeaders: Record<string, unknown> = {};
    if (headers.trim()) {
      try {
        const parsed = JSON.parse(headers) as unknown;
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          toast('Extra headers must be a JSON object');
          return;
        }
        parsedHeaders = parsed as Record<string, unknown>;
      } catch {
        toast('Extra headers JSON is invalid');
        return;
      }
    }
    const refresh = Number(refreshInterval);
    if (!Number.isFinite(refresh) || refresh <= 0) {
      toast('Refresh interval must be greater than 0');
      return;
    }
    setIsSubmittingApi(true);
    try {
      await createSource({
        name: trimmedName,
        type: 'api',
        url: trimmedUrl,
        metadata: {
          auth_type: authType,
          api_key: authType === 'none' ? '' : apiKey,
          refresh_interval_hours: refresh,
          headers: parsedHeaders,
          schema_notes: schemaNotes.trim(),
        },
      });
      toast('API source connected');
      setApiName('');
      setApiUrl('');
      setAuthType('none');
      setApiKey('');
      setHeaders('');
      setRefreshInterval('24');
      setSchemaNotes('');
    } catch {
      toast('Failed to connect API source');
    } finally {
      setIsSubmittingApi(false);
    }
  };

  const removeSource = async (id: string) => {
    setDeletingId(id);
    try {
      const res = await fetch(`${API_BASE_URL}/api/knowledge/sources/${id}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        toast('Failed to delete source');
        return;
      }
      setSources((prev) => prev.filter((s) => s.id !== id));
      toast('Source deleted');
    } catch {
      toast('Failed to delete source');
    } finally {
      setDeletingId(null);
    }
  };

  const reindexSource = async (id: string) => {
    setReindexingId(id);
    try {
      const res = await fetch(`${API_BASE_URL}/api/knowledge/sources/${id}/reindex`, {
        method: 'POST',
      });
      if (!res.ok) {
        toast('Failed to reindex source');
        return;
      }
      const updated = (await res.json()) as KnowledgeSourceApi;
      const mapped = mapSource(updated);
      setSources((prev) => prev.map((s) => (s.id === id ? mapped : s)));
      toast(mapped.status === 'ready' ? 'Source reindexed' : 'Reindex completed with warnings');
    } catch {
      toast('Failed to reindex source');
    } finally {
      setReindexingId(null);
    }
  };

  const fileInputAccept = useMemo(
    () => '.pdf,.doc,.docx,.csv,.txt,.xls,.xlsx,.ppt,.pptx,.json',
    [],
  );

  const isBusy = isSubmittingApi || isSubmittingFile || isSubmittingUrl;

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const clearFile = () => {
    setFileName('');
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Knowledge Base</h1>
        <p className="text-text-secondary mt-1">
          Connect documents, websites, and APIs so the AI bot can answer with up-to-date, brand-specific knowledge.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Upload / connection column */}
        <div className="space-y-4 xl:col-span-1">
          <div className="bg-card rounded-lg p-5 border border-border space-y-3">
            <h3 className="text-sm font-semibold text-text-primary">Upload files</h3>
            <p className="text-xs text-text-secondary">
              Add PDFs, docs, CSVs, and more. The system will index them into the vector database.
            </p>
            <div className="space-y-2">
              <input
                ref={fileInputRef}
                type="file"
                accept={fileInputAccept}
                onChange={handleFileSelect}
                className="hidden"
              />
              <input
                type="text"
                value={fileName}
                onChange={(e) => setFileName(e.target.value)}
                placeholder="Select file or type file name"
                className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={openFilePicker}
                  className="flex-1 border border-border px-3 py-2 rounded-lg text-sm font-medium hover:bg-panel transition-colors"
                >
                  Choose file
                </button>
                <button
                  type="button"
                  onClick={clearFile}
                  className="px-3 py-2 rounded-lg text-sm border border-border text-text-secondary hover:bg-panel"
                >
                  Clear
                </button>
              </div>
              <button
                type="button"
                disabled={!fileName.trim() || isBusy}
                onClick={() => void handleFileAdd()}
                className="w-full bg-primary text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isSubmittingFile ? 'Adding file source...' : 'Add file source'}
              </button>
              <p className="text-[11px] text-text-muted">
                This creates a backend source record. File content indexing can be attached to your vector pipeline next.
              </p>
            </div>
          </div>

          <div className="bg-card rounded-lg p-5 border border-border space-y-3">
            <h3 className="text-sm font-semibold text-text-primary">Website / help center URLs</h3>
            <p className="text-xs text-text-secondary">
              Add public URLs (FAQ, policy pages, help center). The crawler will keep them in sync.
            </p>
            <div className="space-y-2">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://yourstore.com/help/shipping"
                className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <button
                type="button"
                disabled={!url.trim() || isBusy}
                onClick={() => void handleUrlAdd()}
                className="w-full bg-primary text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isSubmittingUrl ? 'Adding URL source...' : 'Add URL source'}
              </button>
            </div>
          </div>

          <div className="bg-card rounded-lg p-5 border border-border space-y-3">
            <h3 className="text-sm font-semibold text-text-primary">API knowledge source</h3>
            <p className="text-xs text-text-secondary">
              Connect an API that the AI can call for live answers (for example: order status, inventory, delivery slots).
            </p>
            <form onSubmit={handleApiAdd} className="space-y-3 text-xs">
              <div>
                <label className="block mb-1 font-medium text-text-primary">API name</label>
                <input
                  type="text"
                  value={apiName}
                  onChange={(e) => setApiName(e.target.value)}
                  placeholder="Orders API (Shopify)"
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block mb-1 font-medium text-text-primary">Base URL</label>
                <input
                  type="url"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  placeholder="https://api.yourstore.com/orders"
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block mb-1 font-medium text-text-primary">Auth type</label>
                  <select
                    value={authType}
                    onChange={(e) => setAuthType(e.target.value as typeof authType)}
                    className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="none">None</option>
                    <option value="api_key">API key header</option>
                    <option value="bearer">Bearer token</option>
                  </select>
                </div>
                <div>
                  <label className="block mb-1 font-medium text-text-primary">Refresh interval (hours)</label>
                  <input
                    type="number"
                    min={1}
                    value={refreshInterval}
                    onChange={(e) => setRefreshInterval(e.target.value)}
                    className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              </div>
              {authType !== 'none' && (
                <div>
                  <label className="block mb-1 font-medium text-text-primary">
                    API key / token (stored server-side)
                  </label>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="sk_live_..."
                    className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              )}
              <div>
                <label className="block mb-1 font-medium text-text-primary">
                  Extra headers (JSON)
                </label>
                <textarea
                  value={headers}
                  onChange={(e) => setHeaders(e.target.value)}
                  placeholder={`{ "X-Store-Id": "my-store", "Accept": "application/json" }`}
                  rows={3}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block mb-1 font-medium text-text-primary">
                  Schema mapping notes
                </label>
                <textarea
                  value={schemaNotes}
                  onChange={(e) => setSchemaNotes(e.target.value)}
                  placeholder="Example: field `order_number` maps to user-facing `Order ID`, `eta` maps to delivery estimate."
                  rows={3}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <p className="mt-1 text-[11px] text-text-muted">
                  These notes help your LangChain / tool configuration know how to turn raw API fields into natural language answers.
                </p>
              </div>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isBusy}
                  className="bg-primary text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {isSubmittingApi ? 'Connecting API source...' : 'Connect API source'}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Data sources table */}
        <div className="bg-sidebar rounded-lg p-6 border border-border xl:col-span-2 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-text-primary">Data sources</h3>
              <p className="text-xs text-text-secondary">
                This is what feeds your vector database and retrieval layer.
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex-1 flex items-center justify-center py-12">
              <p className="text-sm text-text-secondary">Loading knowledge sources...</p>
            </div>
          ) : sources.length === 0 ? (
            <div className="flex-1 flex items-center justify-center py-12">
              <p className="text-sm text-text-secondary">
                No knowledge sources yet. Upload a file, add a URL, or connect an API on the left.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto -mx-4 sm:mx-0">
              <table className="min-w-full text-xs border-t border-border">
                <thead>
                  <tr className="bg-panel text-text-muted">
                    <th className="text-left px-4 py-2 font-medium">Source name</th>
                    <th className="text-left px-4 py-2 font-medium">Type</th>
                    <th className="text-left px-4 py-2 font-medium">Status</th>
                    <th className="text-left px-4 py-2 font-medium">Chunks</th>
                    <th className="text-left px-4 py-2 font-medium">Last updated</th>
                    <th className="text-right px-4 py-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-card divide-y divide-border">
                  {sources.map((s) => (
                    <tr key={s.id}>
                      <td className="px-4 py-2 text-text-primary">
                        <p>{s.name}</p>
                        {s.type === 'api' ? (
                          <div className="mt-1 space-y-0.5 text-[10px] text-text-muted">
                            {s.url ? <p>Base URL: {s.url}</p> : null}
                            <p>
                              Auth: {s.authType || 'none'}
                              {typeof s.refreshHours === 'number' ? ` • Refresh: ${s.refreshHours}h` : ''}
                            </p>
                            {s.headerKeys && s.headerKeys.length > 0 ? (
                              <p>Headers: {s.headerKeys.join(', ')}</p>
                            ) : null}
                            {s.schemaNotes ? <p>Schema notes: {s.schemaNotes}</p> : null}
                          </div>
                        ) : null}
                      </td>
                      <td className="px-4 py-2 capitalize text-text-secondary">
                        {s.type === 'file' && 'File'}
                        {s.type === 'url' && 'URL'}
                        {s.type === 'api' && 'API'}
                      </td>
                      <td className="px-4 py-2">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            s.status === 'ready'
                              ? 'bg-status-success/10 text-status-success'
                              : s.status === 'error'
                                ? 'bg-status-error/10 text-status-error'
                                : 'bg-status-warning/10 text-status-warning'
                          }`}
                        >
                          {s.status === 'ready' ? 'READY' : s.status === 'error' ? 'ERROR' : 'INDEXING'}
                        </span>
                        {s.status === 'error' && s.lastError ? (
                          <p className="mt-1 text-[10px] text-status-error max-w-[260px] break-words">
                            {s.lastError}
                          </p>
                        ) : null}
                      </td>
                      <td className="px-4 py-2 text-text-secondary">
                        {s.type === 'api' ? 'live' : s.chunks}
                      </td>
                      <td className="px-4 py-2 text-text-secondary">{s.lastUpdated}</td>
                      <td className="px-4 py-2 text-right">
                        <button
                          type="button"
                          disabled={reindexingId === s.id}
                          onClick={() => void reindexSource(s.id)}
                          className="mr-3 text-[11px] text-primary hover:underline disabled:opacity-60 disabled:no-underline"
                        >
                          {reindexingId === s.id ? 'Reindexing...' : 'Reindex'}
                        </button>
                        <button
                          type="button"
                          disabled={deletingId === s.id}
                          onClick={() => void removeSource(s.id)}
                          className="text-[11px] text-status-error hover:underline disabled:opacity-60 disabled:no-underline"
                        >
                          {deletingId === s.id ? 'Deleting...' : 'Delete'}
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
  );
}
