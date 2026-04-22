const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';

function authJsonHeaders(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('auth_token');
    if (token) h.Authorization = `Bearer ${token}`;
  }
  return h;
}

export async function signMediaUpload(params: {
  type: 'voice' | 'image' | 'file';
  contentType: string;
  sizeBytes: number;
  durationSeconds?: number;
}): Promise<{ upload_url: string; object_key: string; expires_in: number }> {
  const res = await fetch(`${API_BASE}/api/upload/sign`, {
    method: 'POST',
    headers: authJsonHeaders(),
    body: JSON.stringify({
      type: params.type,
      content_type: params.contentType,
      size_bytes: params.sizeBytes,
      duration_seconds: params.durationSeconds,
    }),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => '');
    throw new Error(t || `sign failed (${res.status})`);
  }
  return (await res.json()) as { upload_url: string; object_key: string; expires_in: number };
}

export async function putToSignedUrl(uploadUrl: string, body: Blob, contentType: string): Promise<void> {
  const res = await fetch(uploadUrl, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body,
  });
  if (!res.ok) throw new Error(`upload failed (${res.status})`);
}

export type MediaMetaPayload = Record<string, unknown>;

/** Upload a browser attachment (blob/data URL) to R2; returns metadata for message_metadata JSON. */
export async function uploadAttachmentToR2(att: {
  type: 'photo' | 'voice' | 'file' | 'video';
  name: string;
  url: string;
  durationSeconds?: number;
}): Promise<MediaMetaPayload> {
  const res = await fetch(att.url);
  const blob = await res.blob();
  const ct =
    blob.type ||
    (att.type === 'voice'
      ? 'audio/webm'
      : att.type === 'photo'
        ? 'image/jpeg'
        : att.type === 'video'
          ? 'video/mp4'
          : 'application/octet-stream');
  const signType = att.type === 'photo' ? 'image' : att.type === 'voice' ? 'voice' : 'file';
  const sign = await signMediaUpload({
    type: signType,
    contentType: ct,
    sizeBytes: blob.size,
    durationSeconds: att.durationSeconds,
  });
  await putToSignedUrl(sign.upload_url, blob, ct);
  const storedType =
    signType === 'image' ? 'image' : signType === 'voice' ? 'voice' : att.type === 'video' ? 'video' : 'file';
  const meta: MediaMetaPayload = {
    type: storedType,
    object_key: sign.object_key,
    mime_type: ct,
    size_bytes: blob.size,
  };
  if (att.type === 'file' || att.type === 'photo' || att.type === 'video') meta.filename = att.name;
  if (att.type === 'voice' && typeof att.durationSeconds === 'number') {
    meta.duration_seconds = att.durationSeconds;
  }
  return meta;
}
