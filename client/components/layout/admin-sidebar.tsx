'use client';

import { LayoutDashboard, Inbox, Users, Building2, TrendingUp, BookOpen, Settings } from 'lucide-react';
import { SidebarBase } from './sidebar-base';

const menuItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/admin/dashboard' },
  { icon: Inbox, label: 'Inbox', path: '/admin/inbox' },
  { icon: Users, label: 'Agents', path: '/admin/agents' },
  { icon: Building2, label: 'Tenants', path: '/admin/tenants' },
  { icon: TrendingUp, label: 'Analytics', path: '/admin/analytics' },
  { icon: BookOpen, label: 'Knowledge Base', path: '/admin/knowledge-base' },
  { icon: Settings, label: 'Settings', path: '/admin/settings' },
];

export function AdminSidebar() {
  return <SidebarBase menuItems={menuItems} title="Arabia Dropshipping" />;
}
