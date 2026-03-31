'use client';

import { useEffect, useMemo, useState } from 'react';
import { MessageCircle, Bot, Users, CircleDot, Languages, Activity } from 'lucide-react';
import { KPICard } from '@/components/cards/kpi-card';
import { LineChartComponent } from '@/components/charts/line-chart';
import { PieChartComponent } from '@/components/charts/pie-chart';
import { useToast } from '@/contexts/ToastContext';

const iconClass = 'w-6 h-6 text-primary';
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

interface DashboardAnalyticsApi {
  total_conversations: number;
  total_conversations_change_percent: number;
  total_messages: number;
  total_messages_change_percent: number;
  ai_handled_percent: number;
  total_agents: number;
  active_agents: number;
  period_days: number;
}

interface AgentActivityApi {
  days: Record<string, { customer: number; agent: number; ai: number }>;
}

interface LanguageDistributionApi {
  languages: Array<{ language: string; count: number; percent: number }>;
  period_days: number;
}

export default function AdminDashboard() {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardAnalyticsApi | null>(null);
  const [agentActivity, setAgentActivity] = useState<Array<{ name: string; active: number }>>([]);
  const [languageDistribution, setLanguageDistribution] = useState<Array<{ name: string; value: number }>>([]);

  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      setIsLoading(true);
      setIsError(false);
      try {
        const [dashboardRes, activityRes, languagesRes] = await Promise.all([
          fetch(`${API_BASE}/api/analytics/dashboard?tenant_id=${TENANT_ID}&days=7`),
          fetch(`${API_BASE}/api/analytics/agent-activity?tenant_id=${TENANT_ID}&days=7`),
          fetch(`${API_BASE}/api/analytics/language-distribution?tenant_id=${TENANT_ID}&days=30`),
        ]);

        if (!dashboardRes.ok || !activityRes.ok || !languagesRes.ok) {
          throw new Error('Failed to fetch dashboard analytics');
        }

        const dashboardData = (await dashboardRes.json()) as DashboardAnalyticsApi;
        const activityData = (await activityRes.json()) as AgentActivityApi;
        const languagesData = (await languagesRes.json()) as LanguageDistributionApi;

        if (cancelled) return;

        const activitySeries = Object.entries(activityData.days)
          .sort(([a], [b]) => (a > b ? 1 : -1))
          .map(([isoDate, counts]) => ({
            name: new Date(isoDate).toLocaleDateString(undefined, { weekday: 'short' }),
            active: counts.agent ?? 0,
          }));

        setDashboard(dashboardData);
        setAgentActivity(activitySeries);
        setLanguageDistribution(
          languagesData.languages.map((l) => ({
            name: l.language,
            value: Number(l.percent.toFixed(2)),
          })),
        );
      } catch {
        if (!cancelled) {
          setIsError(true);
          toast('Failed to load dashboard analytics');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }
    void loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [toast]);

  const totalConversations = dashboard?.total_conversations ?? 0;
  const totalMessages = dashboard?.total_messages ?? 0;
  const aiHandledPercent = dashboard?.ai_handled_percent ?? 0;
  const aiHandledMessages = Math.round(totalMessages * (aiHandledPercent / 100));
  const totalAgents = dashboard?.total_agents ?? 0;
  const activeAgents = dashboard?.active_agents ?? 0;
  const conversationsChange = dashboard?.total_conversations_change_percent ?? 0;
  const conversationsChangeType = conversationsChange >= 0 ? 'positive' : 'negative';
  const formattedConversationsChange = `${conversationsChange >= 0 ? '+' : ''}${conversationsChange.toFixed(1)}% from last week`;
  const hasLanguageData = useMemo(
    () => languageDistribution.some((l) => l.value > 0),
    [languageDistribution],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
        <p className="text-text-secondary mt-1">System overview and key metrics</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Total Conversations"
          value={totalConversations.toLocaleString()}
          change={formattedConversationsChange}
          changeType={conversationsChangeType}
          icon={<MessageCircle className={iconClass} />}
        />
        <KPICard
          title="AI Handled"
          value={aiHandledMessages.toLocaleString()}
          change={`${aiHandledPercent.toFixed(1)}% of total`}
          changeType="positive"
          icon={<Bot className={iconClass} />}
        />
        <KPICard
          title="Total Agents"
          value={totalAgents}
          change={`${totalAgents} account${totalAgents === 1 ? '' : 's'}`}
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
          {isLoading ? (
            <div className="h-[280px] flex items-center justify-center text-sm text-text-secondary">
              Loading activity...
            </div>
          ) : isError || agentActivity.length === 0 ? (
            <div className="h-[280px] flex items-center justify-center text-sm text-text-secondary">
              No activity data available.
            </div>
          ) : (
            <LineChartComponent data={agentActivity} dataKey="active" height={280} />
          )}
        </div>
        <div className="bg-white rounded-lg p-6 border border-border shadow-sm">
          <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
            <Languages className="w-5 h-5 text-primary" />
            Language Distribution
          </h3>
          {isLoading ? (
            <div className="h-[280px] flex items-center justify-center text-sm text-text-secondary">
              Loading language distribution...
            </div>
          ) : isError || !hasLanguageData ? (
            <div className="h-[280px] flex items-center justify-center text-sm text-text-secondary">
              No language data available.
            </div>
          ) : (
            <PieChartComponent data={languageDistribution} height={280} />
          )}
        </div>
      </div>

    </div>
  );
}
