'use client';

import { redirect } from 'next/navigation';

export default function AgentSettingsRedirectPage() {
  redirect('/agent/notifications');
}
