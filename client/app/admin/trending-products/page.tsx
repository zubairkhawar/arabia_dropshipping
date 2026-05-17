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

// Only JPEG/PNG are allowed because Meta's WhatsApp Cloud API only accepts
// those when sending an image by link — keeping uploads to these formats
// means every stored product image is guaranteed deliverable on WhatsApp.
const ALLOWED_IMAGE_MIMES = new Set(['image/jpeg', 'image/jpg', 'image/png']);
const ALLOWED_IMAGE_EXTS = ['.jpg', '.jpeg', '.png'];

const isAllowedImageFile = (file: File): boolean => {
  const mime = (file.type || '').toLowerCase();
  if (mime && ALLOWED_IMAGE_MIMES.has(mime)) return true;
  // Some browsers leave `type` empty for drag-and-drop; fall back to ext.
  const name = (file.name || '').toLowerCase();
  return ALLOWED_IMAGE_EXTS.some((ext) => name.endsWith(ext));
};

const partitionAllowedImages = (
  files: File[],
): { ok: File[]; rejected: File[] } => {
  const ok: File[] = [];
  const rejected: File[] = [];
  for (const f of files) {
    if (isAllowedImageFile(f)) ok.push(f);
    else rejected.push(f);
  }
  return { ok, rejected };
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
  unit_pieces?: number | null;
  image_url: string | null;
  image_key: string | null;
  image_display_url: string | null;
  image_urls?: string[];
  image_keys?: string[];
  image_display_urls?: string[];
  description: string | null;
  display_order: number;
  is_active: boolean;
  is_trending: boolean;
}

interface UploadSignOut {
  upload_url: string;
  object_key: string;
  expires_in: number;
}

function authHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const h: Record<string, string> = { Accept: 'application/json' };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function fetchTrendingApi(
  endpoint: string,
  init: RequestInit = {},
  query?: Record<string, string>,
): Promise<Response> {
  const cleanEndpoint = endpoint
    ? endpoint.startsWith('/')
      ? endpoint
      : `/${endpoint}`
    : '';

  const buildUrl = (withTrailingSlash: boolean) => {
    const base = `${API_BASE}/api/admin/trending-products${withTrailingSlash && !cleanEndpoint ? '/' : ''}${cleanEndpoint}`;
    if (!query) return base;
    const u = new URL(base);
    Object.entries(query).forEach(([k, v]) => u.searchParams.set(k, v));
    return u.toString();
  };

  let res = await fetch(buildUrl(false), init);
  // Compatibility fallback for older deployments that only match trailing slash for collection routes.
  if (res.status === 404 && !cleanEndpoint) {
    res = await fetch(buildUrl(true), init);
  }
  return res;
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
  const [formUnitPieces, setFormUnitPieces] = useState('');
  const [formOrder, setFormOrder] = useState('1');
  const [formActive, setFormActive] = useState(true);
  const [formTrending, setFormTrending] = useState(true);
  const [formDesc, setFormDesc] = useState('');
  const [formImageKeys, setFormImageKeys] = useState<string[]>([]);
  const [formImageUrls, setFormImageUrls] = useState<string[]>([]);
  const [formImagePreviews, setFormImagePreviews] = useState<string[]>([]);
  const [formNewFilePreviews, setFormNewFilePreviews] = useState<string[]>([]);
  const [formFiles, setFormFiles] = useState<File[]>([]);
  const [uploadDragOver, setUploadDragOver] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<TrendingProductRow | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [previewRow, setPreviewRow] = useState<TrendingProductRow | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchTrendingApi('', { headers: authHeaders() }, { country });
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
        (p.description || '').toLowerCase().includes(q) ||
        p.currency.toLowerCase().includes(q) ||
        String(p.price).includes(q),
    );
  }, [items, search]);

  const openCreate = () => {
    setEditing(null);
    setFormName('');
    setFormPrice('');
    setFormCurrency(CURRENCY_BY_COUNTRY[country]);
    setFormCategory(CATEGORIES[0]);
    setFormUnitPieces('');
    const nextOrder = items.length ? Math.min(100, Math.max(...items.map((i) => i.display_order)) + 1) : 1;
    setFormOrder(String(nextOrder));
    setFormActive(true);
    setFormTrending(true);
    setFormDesc('');
    setFormImageKeys([]);
    setFormImageUrls([]);
    setFormImagePreviews([]);
    setFormNewFilePreviews([]);
    setFormFiles([]);
    setFormOpen(true);
  };

  const openEdit = (row: TrendingProductRow) => {
    setEditing(row);
    setFormName(row.product_name);
    setFormPrice(String(row.price));
    setFormCurrency(row.currency);
    setFormCategory(row.category);
    setFormUnitPieces(row.unit_pieces ? String(row.unit_pieces) : '');
    setFormOrder(String(row.display_order));
    setFormActive(row.is_active);
    setFormTrending(row.is_trending);
    setFormDesc(row.description || '');
    const existingKeys = Array.isArray(row.image_keys) && row.image_keys.length
      ? row.image_keys.filter(Boolean)
      : (row.image_key ? [row.image_key] : []);
    const existingUrls = Array.isArray(row.image_urls) && row.image_urls.length
      ? row.image_urls.filter(Boolean)
      : (row.image_url ? [row.image_url] : []);
    const existingPreviewUrls = Array.isArray(row.image_display_urls) && row.image_display_urls.length
      ? row.image_display_urls.filter(Boolean)
      : (row.image_display_url ? [row.image_display_url] : existingUrls);
    setFormImageKeys(existingKeys);
    setFormImageUrls(existingUrls);
    setFormImagePreviews(existingPreviewUrls);
    setFormNewFilePreviews([]);
    setFormFiles([]);
    setFormOpen(true);
  };

  const uploadImagesIfNeeded = async (): Promise<{ image_keys: string[]; image_urls: string[] }> => {
    if (!formFiles.length) {
      return { image_keys: formImageKeys, image_urls: formImageUrls };
    }
    const keys: string[] = [...formImageKeys];
    const urls: string[] = [...formImageUrls];
    for (const formFile of formFiles) {
      const fd = new FormData();
      fd.append('country', editing?.country ?? country);
      fd.append('file', formFile);
      const res = await fetch(`${API_BASE}/api/upload/product-image`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}` },
        body: fd,
      });
      // Backward-compatible fallback: older backend builds may not expose /product-image yet.
      if (res.status === 404) {
        const signRes = await fetch(`${API_BASE}/api/upload/sign`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            type: 'image',
            content_type: formFile.type || 'application/octet-stream',
            size_bytes: formFile.size,
          }),
        });
        if (!signRes.ok) {
          const err = await signRes.json().catch(() => ({}));
          const msg =
            typeof (err as { detail?: string }).detail === 'string'
              ? (err as { detail: string }).detail
              : 'Upload failed';
          throw new Error(msg);
        }
        const signed = (await signRes.json()) as UploadSignOut;
        const putRes = await fetch(signed.upload_url, {
          method: 'PUT',
          headers: { 'Content-Type': formFile.type || 'application/octet-stream' },
          body: formFile,
        });
        if (!putRes.ok) {
          throw new Error('Upload failed');
        }
        keys.push(signed.object_key);
        continue;
      }
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
      keys.push(out.object_key);
      const maybeUrl = (out.image_url || '').trim();
      if (maybeUrl) urls.push(maybeUrl);
    }
    return {
      image_keys: keys,
      image_urls: urls,
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
    const unitRaw = formUnitPieces.trim();
    let unitPieces: number | null = null;
    if (unitRaw !== '') {
      const u = Number(unitRaw);
      if (!Number.isInteger(u) || u <= 0) {
        toast('Unit (pieces) must be a positive whole number or left empty');
        return;
      }
      unitPieces = u;
    }
    if (!name) {
      toast('Product name is required');
      return;
    }
    if (!formFiles.length && !formImageKeys.length) {
      toast('At least one product image is required');
      return;
    }
    const parsedOrder = parseInt(formOrder, 10);
    const order =
      Number.isFinite(parsedOrder) && parsedOrder >= 1 && parsedOrder <= 100
        ? parsedOrder
        : 1;
    setSaving(true);
    try {
      const { image_keys, image_urls } = await uploadImagesIfNeeded();
      const body = {
        country: editing?.country ?? country,
        product_name: name,
        price: priceNum,
        currency: formCurrency,
        category: formCategory,
        unit_pieces: unitPieces,
        image_keys: image_keys.length ? image_keys : undefined,
        image_key: image_keys[0] ?? undefined,
        image_urls: image_urls.length ? image_urls : undefined,
        image_url: image_urls[0] ?? undefined,
        description: formDesc.trim() || null,
        display_order: order,
        is_active: formActive,
        is_trending: formTrending,
      };
      if (editing) {
        const res = await fetchTrendingApi(`/${editing.id}`, {
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
        const res = await fetchTrendingApi('', {
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
      const res = await fetchTrendingApi(`/${deleteTarget.id}`, {
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
    <div className="flex flex-col gap-4 md:gap-6 p-3 md:p-6 max-w-6xl mx-auto w-full">
      <div className="rounded-lg border border-border bg-panel p-3 md:p-5 shadow-sm">
        <h1 className="text-lg md:text-xl font-semibold text-text-primary">Product Management</h1>
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
                    <th className="px-4 py-2 font-medium">Trending</th>
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
                        {!p.is_active ? (
                          <span className="text-text-muted">Inactive</span>
                        ) : p.is_trending ? (
                          <span className="text-emerald-600">Trending</span>
                        ) : (
                          <span className="text-text-muted">Not Trending</span>
                        )}
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
                  <div className="text-xs text-text-muted">
                    {!p.is_active ? 'Inactive' : p.is_trending ? 'Trending' : 'Not Trending'}
                  </div>
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
                  Unit (pieces) (optional)
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={formUnitPieces}
                    onChange={(e) => setFormUnitPieces(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-scaffold px-3 py-2 text-sm"
                    placeholder="e.g. 12"
                  />
                </label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="rounded-lg border border-border bg-scaffold p-3">
                  <div className="text-xs font-medium text-text-secondary">Status</div>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <span className="text-sm text-text-primary">{formActive ? 'Active' : 'Inactive'}</span>
                    <button
                      type="button"
                      aria-label="Toggle status"
                      onClick={() => setFormActive((v) => !v)}
                      className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${
                        formActive ? 'bg-primary' : 'bg-gray-300'
                      }`}
                    >
                      <span
                        className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                          formActive ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>
                  <p className="mt-2 text-[11px] leading-snug text-text-muted">
                    Master switch. If inactive, the bot will not send this product to customers, regardless of trending.
                  </p>
                </div>
                <div className="rounded-lg border border-border bg-scaffold p-3">
                  <div className="text-xs font-medium text-text-secondary">Trending</div>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <span className="text-sm text-text-primary">{formTrending ? 'On' : 'Off'}</span>
                    <button
                      type="button"
                      aria-label="Toggle trending"
                      onClick={() => setFormTrending((v) => !v)}
                      className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${
                        formTrending ? 'bg-primary' : 'bg-gray-300'
                      }`}
                    >
                      <span
                        className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                          formTrending ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>
                  <p className="mt-2 text-[11px] leading-snug text-text-muted">
                    When on, the product appears in the bot&apos;s trending list. Ignored if Status is inactive.
                  </p>
                </div>
              </div>
              <div>
                <span className="text-xs font-medium text-text-secondary">Product Images *</span>
                <label
                  className={`mt-2 flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed p-6 text-center transition-colors ${
                    uploadDragOver ? 'border-blue-500 bg-blue-50' : 'border-border bg-scaffold'
                  }`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setUploadDragOver(true);
                  }}
                  onDragLeave={() => setUploadDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setUploadDragOver(false);
                    const dropped = Array.from(e.dataTransfer.files || []);
                    const { ok, rejected } = partitionAllowedImages(dropped);
                    if (rejected.length) {
                      toast(
                        `Only JPG, JPEG, and PNG images are allowed. Skipped: ${rejected
                          .map((f) => f.name)
                          .join(', ')}`,
                      );
                    }
                    if (!ok.length) return;
                    setFormFiles((prev) => [...prev, ...ok]);
                    setFormNewFilePreviews((prev) => [...prev, ...ok.map((f) => URL.createObjectURL(f))]);
                  }}
                >
                  <input
                    type="file"
                    accept="image/jpeg,image/png,.jpg,.jpeg,.png"
                    multiple
                    className="hidden"
                    onChange={(e) => {
                      const selected = Array.from(e.target.files || []);
                      const { ok, rejected } = partitionAllowedImages(selected);
                      if (rejected.length) {
                        toast(
                          `Only JPG, JPEG, and PNG images are allowed. Skipped: ${rejected
                            .map((f) => f.name)
                            .join(', ')}`,
                        );
                      }
                      if (!ok.length) {
                        e.currentTarget.value = '';
                        return;
                      }
                      setFormFiles((prev) => [...prev, ...ok]);
                      setFormNewFilePreviews((prev) => [...prev, ...ok.map((f) => URL.createObjectURL(f))]);
                      e.currentTarget.value = '';
                    }}
                  />
                  <div className="text-base font-semibold text-text-primary">Upload files</div>
                  <div className="mt-1 text-sm text-text-secondary">Drag & drop or click to browse.</div>
                  <div className="mt-1 text-xs text-text-muted">JPG, JPEG, PNG</div>
                  <div className="mt-2 text-xs text-text-muted">
                    {formFiles.length ? `${formFiles.length} new image(s) selected` : 'No new files selected'}
                  </div>
                </label>
                {(formImagePreviews.length > 0 || formNewFilePreviews.length > 0) && (
                  <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {formImagePreviews.map((src, idx) => (
                      <div key={`existing-${src}-${idx}`} className="relative rounded-lg border border-border overflow-hidden bg-scaffold h-24 flex items-center justify-center">
                        <button
                          type="button"
                          title="Remove image"
                          onClick={() => {
                            setFormImagePreviews((prev) => prev.filter((_, i) => i !== idx));
                            setFormImageKeys((prev) => prev.filter((_, i) => i !== idx));
                            setFormImageUrls((prev) => prev.filter((_, i) => i !== idx));
                          }}
                          className="absolute right-1 top-1 z-10 rounded-full bg-black/60 p-1 text-white hover:bg-black/80"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={src} alt="" className="h-full w-full object-cover" />
                      </div>
                    ))}
                    {formNewFilePreviews.map((src, idx) => (
                      <div key={`new-${src}-${idx}`} className="relative rounded-lg border border-border overflow-hidden bg-scaffold h-24 flex items-center justify-center">
                        <button
                          type="button"
                          title="Remove image"
                          onClick={() => {
                            URL.revokeObjectURL(src);
                            setFormNewFilePreviews((prev) => prev.filter((_, i) => i !== idx));
                            setFormFiles((prev) => prev.filter((_, i) => i !== idx));
                          }}
                          className="absolute right-1 top-1 z-10 rounded-full bg-black/60 p-1 text-white hover:bg-black/80"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={src} alt="" className="h-full w-full object-cover" />
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <label className="block text-xs font-medium text-text-secondary">
                Description (optional)
                <textarea
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  rows={6}
                  className="mt-1 w-full resize-y rounded-lg border border-border bg-scaffold px-3 py-2 text-sm leading-relaxed [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
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
