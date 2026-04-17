'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Image as ImageIcon, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

type CountryCode = 'UAE' | 'KSA' | 'PK';

const COUNTRY_TABS: { code: CountryCode; label: string; flag: string }[] = [
  { code: 'UAE', label: 'UAE', flag: '🇦🇪' },
  { code: 'KSA', label: 'KSA', flag: '🇸🇦' },
  { code: 'PK', label: 'Pakistan', flag: '🇵🇰' },
];

const CURRENCY_BY_COUNTRY: Record<CountryCode, string> = {
  UAE: 'AED',
  KSA: 'SAR',
  PK: 'PKR',
};

const CATEGORIES = [
  'Electronics',
  'Fashion',
  'Beauty',
  'Home & Living',
  'Toys & Games',
  'Sports & Outdoors',
  'Pets',
  'Automotive',
  'Baby & Kids',
  'Books & Media',
  'Office & Stationery',
  'Groceries & Food',
  'Health & Wellness',
  'Jewelry & Watches',
  'Luggage & Travel',
  'Tools & Home Improvement',
  'Garden & Outdoor',
  'Musical Instruments',
  'Art & Crafts',
  'Party & Occasion',
] as const;

interface TrendingProductRow {
  id: number;
  country: string;
  product_name: string;
  price: number;
  currency: string;
  category: string;
  image_url: string | null;
  image_key: string | null;
  image_display_url: string | null;
  description: string | null;
  display_order: number;
  is_active: boolean;
}

function authHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const h: Record<string, string> = { Accept: 'application/json' };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

export default function AdminTrendingProductsPage() {
  const { toast } = useToast();
  const [country, setCountry] = useState<CountryCode>('UAE');
  const [search, setSearch] = useState('');
  const [items, setItems] = useState<TrendingProductRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [mounted, setMounted] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TrendingProductRow | null>(null);
  const [saving, setSaving] = useState(false);
  const [formName, setFormName] = useState('');
  const [formPrice, setFormPrice] = useState('');
  const [formCurrency, setFormCurrency] = useState('AED');
  const [formCategory, setFormCategory] = useState<string>(CATEGORIES[0]);
  const [formOrder, setFormOrder] = useState('1');
  const [formActive, setFormActive] = useState(true);
  const [formDesc, setFormDesc] = useState('');
  const [formImageKey, setFormImageKey] = useState<string | null>(null);
  const [formImageUrl, setFormImageUrl] = useState<string | null>(null);
  const [formImagePreview, setFormImagePreview] = useState<string | null>(null);
  const [formFile, setFormFile] = useState<File | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<TrendingProductRow | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [previewRow, setPreviewRow] = useState<TrendingProductRow | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const url = new URL(`${API_BASE}/api/admin/trending-products`);
      url.searchParams.set('country', country);
      const res = await fetch(url.toString(), { headers: authHeaders() });
      if (res.status === 401) {
        toast('Sign in as admin first');
        setItems([]);
        return;
      }
      if (!res.ok) {
        toast('Failed to load products');
        setItems([]);
        return;
      }
      const data = (await res.json()) as TrendingProductRow[];
      setItems(Array.isArray(data) ? data : []);
    } catch {
      toast('Failed to load products');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [country, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (p) =>
        p.product_name.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q) ||
        String(p.price).includes(q),
    );
  }, [items, search]);

  const openCreate = () => {
    setEditing(null);
    setFormName('');
    setFormPrice('');
    setFormCurrency(CURRENCY_BY_COUNTRY[country]);
    setFormCategory(CATEGORIES[0]);
    const nextOrder = items.length ? Math.min(100, Math.max(...items.map((i) => i.display_order)) + 1) : 1;
    setFormOrder(String(nextOrder));
    setFormActive(true);
    setFormDesc('');
    setFormImageKey(null);
    setFormImageUrl(null);
    setFormImagePreview(null);
    setFormFile(null);
    setFormOpen(true);
  };

  const openEdit = (row: TrendingProductRow) => {
    setEditing(row);
    setFormName(row.product_name);
    setFormPrice(String(row.price));
    setFormCurrency(row.currency);
    setFormCategory(row.category);
    setFormOrder(String(row.display_order));
    setFormActive(row.is_active);
    setFormDesc(row.description || '');
    setFormImageKey(row.image_key);
    setFormImageUrl(row.image_url);
    setFormImagePreview(row.image_display_url || row.image_url);
    setFormFile(null);
    setFormOpen(true);
  };

  const uploadImageIfNeeded = async (): Promise<{ image_key: string | null; image_url: string | null }> => {
    if (!formFile) {
      return { image_key: formImageKey, image_url: formImageUrl };
    }
    const fd = new FormData();
    fd.append('country', editing?.country ?? country);
    fd.append('file', formFile);
    const res = await fetch(`${API_BASE}/api/upload/product-image`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}` },
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg = typeof (err as { detail?: string }).detail === 'string' ? (err as { detail: string }).detail : 'Upload failed';
      throw new Error(msg);
    }
    const out = (await res.json()) as {
      object_key: string;
      image_url: string | null;
      image_display_url: string | null;
    };
    return {
      image_key: out.object_key,
      image_url: (out.image_url || '').trim() || null,
    };
  };

  const saveProduct = async () => {
    const name = formName.trim();
    const priceRaw = formPrice.trim();
    let priceNum: number | null = null;
    if (priceRaw !== '') {
      const n = Number(priceRaw);
      if (!Number.isFinite(n) || n < 0) {
        toast('Price must be a valid non-negative number or left empty');
        return;
      }
      priceNum = n;
    }
    if (!name) {
      toast('Product name is required');
      return;
    }
    if (!editing && !formFile && !formImageKey) {
      toast('Product image is required');
      return;
    }
    const order = parseInt(formOrder, 10);
    if (!Number.isFinite(order) || order < 1 || order > 100) {
      toast('Display order must be 1–100');
      return;
    }
    setSaving(true);
    try {
      const { image_key, image_url } = await uploadImageIfNeeded();
      const body = {
        country: editing?.country ?? country,
        product_name: name,
        price: priceNum,
        currency: formCurrency,
        category: formCategory,
        image_key: image_key ?? undefined,
        image_url: image_url ?? undefined,
        description: formDesc.trim() || null,
        display_order: order,
        is_active: formActive,
      };
      if (editing) {
        const res = await fetch(`${API_BASE}/api/admin/trending-products/${editing.id}`, {
          method: 'PUT',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(typeof (err as { detail?: string }).detail === 'string' ? (err as { detail: string }).detail : 'Save failed');
        }
        toast('Product updated');
      } else {
        const res = await fetch(`${API_BASE}/api/admin/trending-products`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(typeof (err as { detail?: string }).detail === 'string' ? (err as { detail: string }).detail : 'Save failed');
        }
        toast('Product added');
      }
      setFormOpen(false);
      await load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/trending-products/${deleteTarget.id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!res.ok) {
        toast('Delete failed');
        return;
      }
      toast('Product deleted');
      setDeleteTarget(null);
      await load();
    } finally {
      setDeleting(false);
    }
  };

  const countryLabel = COUNTRY_TABS.find((t) => t.code === country)?.label ?? country;

  return (
    <div className="flex flex-col gap-6 p-6 max-w-6xl mx-auto w-full">
      <div className="rounded-lg border border-border bg-panel p-5 shadow-sm">
        <h1 className="text-xl font-semibold text-text-primary">Trending Products Management</h1>
        <p className="text-sm text-text-secondary mt-1">
          Manage products shown when customers ask for trending items (by country).
        </p>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-border pb-3">
        {COUNTRY_TABS.map((t) => (
          <button
            key={t.code}
            type="button"
            onClick={() => setCountry(t.code)}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              country === t.code
                ? 'bg-primary text-white'
                : 'bg-panel border border-border text-text-secondary hover:bg-scaffold'
            }`}
          >
            <span>{t.flag}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          onClick={openCreate}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90"
        >
          <Plus className="h-4 w-4" />
          Add New Product
        </button>
        <div className="relative flex-1 sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input
            type="search"
            placeholder="Search products..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-border bg-scaffold py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted"
          />
        </div>
      </div>

      <div className="rounded-lg border border-border bg-panel shadow-sm overflow-hidden">
        <div className="border-b border-border px-4 py-3 bg-scaffold/50">
          <h2 className="text-sm font-semibold text-text-primary">
            Products — {countryLabel}
          </h2>
        </div>

        {loading ? (
          <div className="p-8 text-center text-text-secondary text-sm">Loading…</div>
        ) : (
          <>
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-text-muted">
                    <th className="px-4 py-2 font-medium w-10">#</th>
                    <th className="px-4 py-2 font-medium">Product Name</th>
                    <th className="px-4 py-2 font-medium">Price</th>
                    <th className="px-4 py-2 font-medium">Category</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium text-right w-36">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p, idx) => (
                    <tr key={p.id} className="border-b border-border last:border-0 hover:bg-scaffold/40">
                      <td className="px-4 py-2 text-text-muted">{idx + 1}</td>
                      <td className="px-4 py-2 font-medium text-text-primary">{p.product_name}</td>
                      <td className="px-4 py-2 text-text-secondary">
                        {p.price} {p.currency}
                      </td>
                      <td className="px-4 py-2 text-text-secondary">{p.category}</td>
                      <td className="px-4 py-2">
                        <span className={p.is_active ? 'text-emerald-600' : 'text-text-muted'}>
                          {p.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right">
                        <div className="inline-flex gap-1">
                          <button
                            type="button"
                            title="Edit"
                            onClick={() => openEdit(p)}
                            className="rounded p-2 text-text-secondary hover:bg-panel hover:text-text-primary"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            title="Delete"
                            onClick={() => setDeleteTarget(p)}
                            className="rounded p-2 text-text-secondary hover:bg-red-50 hover:text-red-700"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            title="Image"
                            onClick={() => setPreviewRow(p)}
                            disabled={!p.image_display_url && !p.image_url}
                            className="rounded p-2 text-text-secondary hover:bg-panel hover:text-text-primary disabled:opacity-40"
                          >
                            <ImageIcon className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="md:hidden divide-y divide-border">
              {filtered.map((p) => (
                <div key={p.id} className="p-4 space-y-2">
                  <div className="font-medium text-text-primary">{p.product_name}</div>
                  <div className="text-sm text-text-secondary">
                    {p.price} {p.currency} · {p.category}
                  </div>
                  <div className="text-xs text-text-muted">{p.is_active ? 'Active' : 'Inactive'}</div>
                  <div className="flex gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => openEdit(p)}
                      className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(p)}
                      className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700"
                    >
                      Delete
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreviewRow(p)}
                      disabled={!p.image_display_url && !p.image_url}
                      className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium disabled:opacity-40"
                    >
                      Image
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {!filtered.length && (
              <div className="p-8 text-center text-text-secondary text-sm">No products for this country yet.</div>
            )}
          </>
        )}
      </div>

      {mounted && formOpen && createPortal(
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" role="dialog">
          <div className="w-full max-w-lg rounded-xl border border-border bg-panel shadow-xl max-h-[90vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3 shrink-0">
              <h3 className="font-semibold text-text-primary">
                {editing ? `Edit Product — ${editing.country}` : `Add New Product — ${country}`}
              </h3>
              <button type="button" onClick={() => setFormOpen(false)} className="rounded p-1 hover:bg-scaffold">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4 p-4 flex-1 min-h-0 overflow-y-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
              <label className="block text-xs font-medium text-text-secondary">
                Product Name *
                <input
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-scaffold px-3 py-2 text-sm"
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs font-medium text-text-secondary">
                  Price (optional)
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    value={formPrice}
                    onChange={(e) => setFormPrice(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-scaffold px-3 py-2 text-sm"
                  />
                </label>
                <label className="block text-xs font-medium text-text-secondary">
                  Currency *
                  <select
                    value={formCurrency}
                    onChange={(e) => setFormCurrency(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-scaffold px-3 py-2 text-sm"
                  >
                    <option value="AED">AED</option>
                    <option value="SAR">SAR</option>
                    <option value="PKR">PKR</option>
                  </select>
                </label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs font-medium text-text-secondary">
                  Category *
                  <select
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-scaffold px-3 py-2 text-sm"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs font-medium text-text-secondary">
                  Display Order * (1–100)
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={formOrder}
                    onChange={(e) => setFormOrder(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-scaffold px-3 py-2 text-sm"
                  />
                </label>
              </div>
              <div>
                <span className="text-xs font-medium text-text-secondary">Status</span>
                <div className="mt-2 flex gap-4 text-sm">
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input type="radio" checked={formActive} onChange={() => setFormActive(true)} />
                    Active
                  </label>
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input type="radio" checked={!formActive} onChange={() => setFormActive(false)} />
                    Inactive
                  </label>
                </div>
              </div>
              <div>
                <span className="text-xs font-medium text-text-secondary">Product Image *</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  className="mt-1 block w-full text-sm"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    setFormFile(f ?? null);
                    if (f) setFormImagePreview(URL.createObjectURL(f));
                  }}
                />
                {formImagePreview && (
                  <div className="mt-2 rounded-lg border border-border overflow-hidden bg-scaffold max-h-48 flex items-center justify-center">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={formImagePreview} alt="" className="max-h-48 w-auto object-contain" />
                  </div>
                )}
              </div>
              <label className="block text-xs font-medium text-text-secondary">
                Description (optional)
                <textarea
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-lg border border-border bg-scaffold px-3 py-2 text-sm"
                />
              </label>
            </div>
            <div className="flex justify-end gap-2 border-t border-border px-4 py-3 shrink-0">
              <button type="button" onClick={() => setFormOpen(false)} className="rounded-lg px-4 py-2 text-sm border border-border">
                Cancel
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => void saveProduct()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {saving ? 'Saving…' : 'Save Product'}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}

      {mounted && deleteTarget && createPortal(
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" role="dialog">
          <div className="w-full max-w-md rounded-xl border border-border bg-panel shadow-xl p-5">
            <h3 className="font-semibold text-text-primary">Delete Product</h3>
            <p className="mt-3 text-sm text-text-secondary">
              Are you sure you want to delete &quot;{deleteTarget.product_name}&quot;? This cannot be undone. The image
              will also be removed from storage when possible.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setDeleteTarget(null)} className="rounded-lg px-4 py-2 text-sm border border-border">
                Cancel
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={() => void confirmDelete()}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {deleting ? 'Deleting…' : 'Delete permanently'}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}

      {mounted && previewRow && createPortal(
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" role="dialog">
          <div className="w-full max-w-lg rounded-xl border border-border bg-panel shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h3 className="font-semibold text-text-primary">Product Image — {previewRow.product_name}</h3>
              <button type="button" onClick={() => setPreviewRow(null)} className="rounded p-1 hover:bg-scaffold">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              {(previewRow.image_display_url || previewRow.image_url) && (
                <div className="rounded-lg border border-border overflow-hidden bg-scaffold flex justify-center">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={previewRow.image_display_url || previewRow.image_url || ''}
                    alt=""
                    className="max-h-72 w-auto object-contain"
                  />
                </div>
              )}
              <div className="text-xs break-all text-text-secondary">
                <span className="font-medium text-text-primary">Image URL: </span>
                {previewRow.image_url || previewRow.image_display_url || '—'}
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const u = previewRow.image_url || previewRow.image_display_url;
                    if (u) void navigator.clipboard.writeText(u).then(() => toast('Copied')).catch(() => toast('Copy failed'));
                  }}
                  className="rounded-lg border border-border px-4 py-2 text-sm"
                >
                  Copy URL
                </button>
                <button type="button" onClick={() => setPreviewRow(null)} className="rounded-lg bg-primary px-4 py-2 text-sm text-white">
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
