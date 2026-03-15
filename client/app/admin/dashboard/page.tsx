'use client';

import { MessageCircle, Bot, Users, CircleDot, Languages, Activity } from 'lucide-react';
import { KPICard } from '@/components/cards/kpi-card';
import { LineChartComponent } from '@/components/charts/line-chart';
import { PieChartComponent } from '@/components/charts/pie-chart';
import { useAgents } from '@/contexts/AgentsContext';

const iconClass = 'w-6 h-6 text-primary';

export default function AdminDashboard() {
  const { agents } = useAgents();

  const agentActivity = [
    { name: 'Mon', active: 12, busy: 3 },
    { name: 'Tue', active: 15, busy: 2 },
    { name: 'Wed', active: 14, busy: 4 },
    { name: 'Thu', active: 18, busy: 3 },
    { name: 'Fri', active: 16, busy: 2 },
    { name: 'Sat', active: 10, busy: 1 },
    { name: 'Sun', active: 8, busy: 1 },
  ];

  const languageDistribution = [
    { name: 'Arabic', value: 45 },
    { name: 'English', value: 35 },
    { name: 'Roman Urdu', value: 20 },
  ];

  const totalAgents = agents.length;
  const activeAgents = Math.min(3, totalAgents); // Mock: e.g. 3 currently active

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
        <p className="text-text-secondary mt-1">System overview and key metrics</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Total Messages"
          value="45,234"
          change="+12.5% from last week"
          changeType="positive"
          icon={<MessageCircle className={iconClass} />}
        />
        <KPICard
          title="AI Handled"
          value="38,456"
          change="85% of total"
          changeType="positive"
          icon={<Bot className={iconClass} />}
        />
        <KPICard
          title="Total Agents"
          value={totalAgents}
          change={`${agents.length} account${agents.length === 1 ? '' : 's'}`}
          changeType="neutral"
          icon={<Users className={iconClass} />}
        />
        <KPICard
          title="Active Agents"
          value={activeAgents}
          change="Currently online"
          changeType="positive"
          icon={<CircleDot className={iconClass} />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" />
            Agent Activity
          </h3>
          <LineChartComponent data={agentActivity} dataKey="active" height={280} />
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
            <Languages className="w-5 h-5 text-primary" />
            Language Distribution
          </h3>
          <PieChartComponent data={languageDistribution} height={280} />
        </div>
      </div>

    </div>
  );
}
