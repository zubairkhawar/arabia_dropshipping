'use client';

import { useState } from 'react';

type SourceType = 'file' | 'url' | 'api';

interface KnowledgeSource {
  id: string;
  name: string;
  type: SourceType;
  status: 'indexing' | 'ready';
  chunks: number;
  lastUpdated: string;
}

export default function AdminKnowledgeBase() {
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

  const addSource = (name: string, type: SourceType) => {
    if (!name.trim()) return;
    setSources((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${type}`,
        name: name.trim(),
        type,
        status: 'ready',
        chunks: type === 'api' ? 0 : 42,
        lastUpdated: new Date().toLocaleString(),
      },
    ]);
  };

  const handleFileMock = () => {
    if (!fileName.trim()) return;
    addSource(fileName, 'file');
    setFileName('');
  };

  const handleUrlAdd = () => {
    if (!url.trim()) return;
    addSource(url, 'url');
    setUrl('');
  };

  const handleApiAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiName.trim() || !apiUrl.trim()) return;
    addSource(apiName, 'api');
    setApiName('');
    setApiUrl('');
    setAuthType('none');
    setApiKey('');
    setHeaders('');
    setRefreshInterval('24');
    setSchemaNotes('');
  };

  const removeSource = (id: string) => {
    setSources((prev) => prev.filter((s) => s.id !== id));
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
                type="text"
                value={fileName}
                onChange={(e) => setFileName(e.target.value)}
                placeholder="Select or mock file name (UI only)"
                className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <button
                type="button"
                onClick={handleFileMock}
                className="w-full bg-primary text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors"
              >
                Add file source
              </button>
              <p className="text-[11px] text-text-muted">
                In production this will open a real file picker and stream content to your vector DB.
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
                onClick={handleUrlAdd}
                className="w-full bg-primary text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors"
              >
                Add URL source
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
                  className="bg-primary text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors"
                >
                  Connect API source
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

          {sources.length === 0 ? (
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
                      <td className="px-4 py-2 text-text-primary">{s.name}</td>
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
                              : 'bg-status-warning/10 text-status-warning'
                          }`}
                        >
                          {s.status === 'ready' ? 'READY' : 'INDEXING'}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-text-secondary">
                        {s.type === 'api' ? 'live' : s.chunks}
                      </td>
                      <td className="px-4 py-2 text-text-secondary">{s.lastUpdated}</td>
                      <td className="px-4 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => removeSource(s.id)}
                          className="text-[11px] text-status-error hover:underline"
                        >
                          Delete
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
