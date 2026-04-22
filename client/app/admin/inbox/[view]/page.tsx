'use client';

import { notFound, useParams } from 'next/navigation';
import AdminInboxShell from '../admin-inbox-shell';

export default function AdminInboxViewPage() {
  const raw = useParams()?.view;
  const view = typeof raw === 'string' ? raw : Array.isArray(raw) ? raw[0] : '';
  if (view !== 'live' && view !== 'closed') {
    notFound();
  }
  return <AdminInboxShell />;
}
