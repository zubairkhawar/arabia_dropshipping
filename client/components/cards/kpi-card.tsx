'use client';

import type { ReactNode } from 'react';

interface KPICardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon?: ReactNode;
}

export function KPICard({ title, value, change, changeType = 'neutral', icon }: KPICardProps) {
  const changeColor = {
    positive: 'text-status-success',
    negative: 'text-status-error',
    neutral: 'text-text-secondary',
  }[changeType];

  return (
    <div className="bg-white rounded-lg p-6 border border-border h-kpi-card flex flex-col justify-between shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-text-secondary">{title}</span>
        {icon && <span className="text-2xl">{icon}</span>}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold text-text-primary">{value}</span>
        {change && (
          <span className={`text-sm font-medium ${changeColor}`}>
            {changeType === 'positive' ? '↑' : changeType === 'negative' ? '↓' : ''} {change}
          </span>
        )}
      </div>
    </div>
  );
}
