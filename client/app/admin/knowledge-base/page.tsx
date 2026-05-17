'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useToast } from '@/contexts/ToastContext';
import { useTenantTimezone } from '@/contexts/TenantTimezoneContext';
import { formatKnowledgeSourceUpdatedInZone } from '@/lib/tenant-time';

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
  viewUrl?: string;
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

/**
 * Open KB preview in a new tab. Huge `data:` URLs (e.g. base64 PDFs) exceed browser URL limits
 * and navigate to about:blank — use a Blob object URL instead.
 */
async function openKnowledgePreview(
  url: string,
  onError: (message: string) => void,
): Promise<void> {
  const trimmed = (url || '').trim();
  if (!trimmed) {
    onError('Nothing to preview');
    return;
  }
  try {
    if (trimmed.startsWith('data:')) {
      let blob: Blob;
      try {
        const res = await fetch(trimmed);
        if (!res.ok) throw new Error(`fetch ${res.status}`);
        blob = await res.blob();
      } catch {
        const comma = trimmed.indexOf(',');
        if (comma < 0) throw new Error('invalid data url');
        const meta = trimmed.slice(0, comma);
        const data = trimmed.slice(comma + 1);
        const mimeMatch = /^data:([^;]+)/.exec(meta);
        const mime = mimeMatch ? mimeMatch[1] : 'application/octet-stream';
        const isBase64 = /;base64$/i.test(meta);
        if (isBase64) {
          const binary = atob(data);
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          blob = new Blob([bytes], { type: mime });
        } else {
          blob = new Blob([decodeURIComponent(data)], { type: mime });
        }
      }
      const objectUrl = URL.createObjectURL(blob);
      const win = window.open(objectUrl, '_blank', 'noopener,noreferrer');
      if (!win) {
        URL.revokeObjectURL(objectUrl);
        onError('Popup blocked. Allow popups for this site to preview files.');
        return;
      }
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 120_000);
      return;
    }
    const win = window.open(trimmed, '_blank', 'noopener,noreferrer');
    if (!win) {
      onError('Popup blocked. Allow popups for this site to open links.');
    }
  } catch {
    onError('Could not open preview');
  }
}

export default function AdminKnowledgeBase() {
  const { toast } = useToast();
  const { timeZone } = useTenantTimezone();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [fileName, setFileName] = useState('');
  const [url, setUrl] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmittingFile, setIsSubmittingFile] = useState(false);
  const [isSubmittingUrl, setIsSubmittingUrl] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [reindexingId, setReindexingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
  const [mounted, setMounted] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!openMenuId) return;
    const handleMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (menuRef.current && target && !menuRef.current.contains(target)) {
        setOpenMenuId(null);
      }
    };
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenMenuId(null);
    };
    document.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleMouseDown);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [openMenuId]);

  useEffect(() => {
    if (!openMenuId) return;
    const handleScrollOrResize = () => setOpenMenuId(null);
    window.addEventListener('scroll', handleScrollOrResize, true);
    window.addEventListener('resize', handleScrollOrResize);
    return () => {
      window.removeEventListener('scroll', handleScrollOrResize, true);
      window.removeEventListener('resize', handleScrollOrResize);
    };
  }, [openMenuId]);

  const mapSource = useCallback((s: KnowledgeSourceApi): KnowledgeSource => {
    const updated = s.updated_at || s.created_at;
    const viewUrl =
      s.type === 'url'
        ? (typeof s.url === 'string' ? s.url : undefined)
        : (typeof s.metadata?.file_data_url === 'string' ? s.metadata.file_data_url : undefined);
    return {
      id: String(s.id),
      name: s.name,
      type: s.type,
      status: s.status === 'ready' ? 'ready' : s.status === 'error' ? 'error' : 'indexing',
      chunks: s.chunk_count,
      lastUpdated: formatKnowledgeSourceUpdatedInZone(updated, timeZone),
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
      viewUrl,
    };
  }, [timeZone]);

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
    setSelectedFile(file);
  };

  const fileToDataUrl = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('file_read_failed'));
      reader.readAsDataURL(file);
    });

  const handleFileAdd = async () => {
    const trimmed = fileName.trim();
    if (!trimmed) {
      toast('Please choose a file');
      return;
    }
    setIsSubmittingFile(true);
    try {
      let fileDataUrl: string | undefined;
      let fileDataBase64: string | undefined;
      let fileText: string | undefined;
      let mimeType: string | undefined;
      if (selectedFile) {
        mimeType = selectedFile.type || 'application/octet-stream';
        fileDataUrl = await fileToDataUrl(selectedFile);
        const comma = fileDataUrl.indexOf(',');
        fileDataBase64 = comma >= 0 ? fileDataUrl.slice(comma + 1) : '';
        if (
          selectedFile.type.startsWith('text/') ||
          selectedFile.type === 'application/json' ||
          selectedFile.type === 'application/csv'
        ) {
          fileText = await selectedFile.text();
        }
      }
      await createSource({
        name: trimmed,
        type: 'file',
        metadata: {
          filename: trimmed,
          mime_type: mimeType,
          file_data_url: fileDataUrl,
          file_data_base64: fileDataBase64,
          file_text: fileText,
        },
      });
      toast('File source added');
      setFileName('');
      setSelectedFile(null);
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

  const isBusy = isSubmittingFile || isSubmittingUrl;

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const clearFile = () => {
    setFileName('');
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="space-y-4 md:space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-text-primary">Knowledge Base</h1>
        <p className="text-text-secondary mt-1 text-sm md:text-base">
          Connect documents and websites so the AI bot can answer with up-to-date, brand-specific knowledge.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 md:gap-6">
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
                No knowledge sources yet. Upload a file or add a URL on the left.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto overflow-y-visible -mx-4 sm:mx-0 admin-no-scrollbar">
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
                        <div className="relative inline-block text-left">
                          <button
                            type="button"
                            onClick={(e) => {
                              const btn = e.currentTarget;
                              const rect = btn.getBoundingClientRect();
                              if (openMenuId === s.id) {
                                setOpenMenuId(null);
                                return;
                              }
                              setMenuPosition({ top: rect.bottom + 6, left: rect.right - 128 });
                              setOpenMenuId(s.id);
                            }}
                            className="px-2 py-1 rounded hover:bg-panel text-text-secondary"
                            aria-label="Open actions menu"
                          >
                            ⋮
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      {mounted && openMenuId && menuPosition && (() => {
        const source = sources.find((x) => x.id === openMenuId);
        if (!source) return null;
        return createPortal(
          <div
            ref={menuRef}
            className="fixed w-32 bg-white border border-border rounded-lg shadow-md z-[1000]"
            style={{ top: `${menuPosition.top}px`, left: `${menuPosition.left}px` }}
          >
            <button
              type="button"
              disabled={!source.viewUrl}
              onClick={() => {
                if (!source.viewUrl) return;
                void openKnowledgePreview(source.viewUrl, (msg) => toast(msg));
                setOpenMenuId(null);
              }}
              className="w-full text-left px-3 py-2 text-[11px] hover:bg-panel disabled:opacity-40"
            >
              View
            </button>
            <button
              type="button"
              disabled={reindexingId === source.id}
              onClick={() => {
                void reindexSource(source.id);
                setOpenMenuId(null);
              }}
              className="w-full text-left px-3 py-2 text-[11px] hover:bg-panel disabled:opacity-40"
            >
              {reindexingId === source.id ? 'Reindexing...' : 'Reindex'}
            </button>
            <button
              type="button"
              disabled={deletingId === source.id}
              onClick={() => {
                void removeSource(source.id);
                setOpenMenuId(null);
              }}
              className="w-full text-left px-3 py-2 text-[11px] text-status-error hover:bg-panel disabled:opacity-40"
            >
              {deletingId === source.id ? 'Deleting...' : 'Delete'}
            </button>
          </div>,
          document.body,
        );
      })()}
    </div>
  );
}
