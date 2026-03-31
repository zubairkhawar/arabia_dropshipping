'use client';

import { useEffect, useMemo, useState } from 'react';
import { useAgents } from '@/contexts/AgentsContext';
import { UserPlus, Trash2, Eye, EyeOff, ChevronLeft, ChevronRight, Copy, Clock, TrendingUp, Pencil, Check, X, Download } from 'lucide-react';
import { AgentActivityBar, useAgentAttendanceData } from '@/components/agents/activity-bar';
import { useOnlineSchedule } from '@/contexts/OnlineScheduleContext';
import { useToast } from '@/contexts/ToastContext';
import { buildSingleAgentPdf, filterByMonth } from '@/lib/attendance-pdf';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const NAME_RE = /^[A-Za-z]+$/;
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://arabia-dropshipping.onrender.com';
const TENANT_ID = 1;

function formatAvgResponse(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}.${Math.round((s / 60) * 10)}m` : `${m}m`;
}

function getDemoPerformanceFromAttendance(
  dayData: { date: Date; hoursWorked: number }[],
  workingDays: number[],
  agentId: string,
): { uptimePercent: number; avgResponseTimeSeconds: number } {
  const now = new Date();
  const from = new Date(now);
  from.setDate(from.getDate() - 29);
  from.setHours(0, 0, 0, 0);
  const workingSet = new Set(workingDays);
  const recent = dayData.filter((d) => d.date >= from && d.date <= now && workingSet.has(d.date.getDay()));
  const worked = recent.filter((d) => d.hoursWorked > 0);
  const uptimePercent = recent.length > 0 ? Math.round((worked.length / recent.length) * 100) : 0;
  const avgHours = worked.length > 0 ? worked.reduce((s, d) => s + d.hoursWorked, 0) / worked.length : 0;
  const idSeed = agentId.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 12;
  const avgResponseTimeSeconds = Math.max(20, Math.round(170 - avgHours * 14 + idSeed));
  return { uptimePercent, avgResponseTimeSeconds };
}

export default function AdminAgents() {
  const { agents, addAgent, removeAgent, updateAgent } = useAgents();
  const { schedule } = useOnlineSchedule();
  const { toast } = useToast();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCreatePassword, setShowCreatePassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [createError, setCreateError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [agentReportMonth, setAgentReportMonth] = useState(() => new Date().getMonth() + 1);
  const [agentReportYear, setAgentReportYear] = useState(() => new Date().getFullYear());
  const [agentReportDownloading, setAgentReportDownloading] = useState(false);
  const [deleteAgentConfirm, setDeleteAgentConfirm] = useState<{ id: string; label: string } | null>(null);

  useEffect(() => {
    if (!selectedId && agents.length > 0) {
      setSelectedId(agents[0].id);
    } else if (selectedId && !agents.find((a) => a.id === selectedId)) {
      setSelectedId(agents[0]?.id ?? null);
    }
  }, [agents, selectedId]);

  useEffect(() => {
    setEditingName(false);
  }, [selectedId]);

  const selectedAgent = useMemo(
    () => agents.find((a) => a.id === selectedId) ?? null,
    [agents, selectedId],
  );
  const { dayData: attendanceDayData } = useAgentAttendanceData(selectedAgent?.id, schedule.workingDays);
  const visibleAttendanceDayData = useMemo(() => {
    if (!selectedAgent) return [];
    const created = new Date(selectedAgent.createdAt);
    if (Number.isNaN(created.getTime())) return attendanceDayData;
    // Avoid fake historical attendance for newly created agents: only show after next day.
    const cutoff = new Date(created);
    cutoff.setHours(0, 0, 0, 0);
    cutoff.setDate(cutoff.getDate() + 1);
    return attendanceDayData.map((d) =>
      d.date < cutoff ? { ...d, hoursWorked: 0, sessions: [] } : d
    );
  }, [attendanceDayData, selectedAgent]);
  const performanceMetrics = useMemo(() => {
    if (!selectedAgent) return { uptimePercent: 0, avgResponseTimeSeconds: 0 };
    return getDemoPerformanceFromAttendance(visibleAttendanceDayData, schedule.workingDays, selectedAgent.id);
  }, [visibleAttendanceDayData, schedule.workingDays, selectedAgent]);

  const toTitle = (value: string) => {
    const v = value.trim().toLowerCase();
    if (!v) return '';
    return v.charAt(0).toUpperCase() + v.slice(1);
  };

  const validateCreateForm = (
    emailValue: string,
    first: string,
    last: string,
    pass: string,
    confirmPass: string,
  ): string | null => {
    if (!emailValue || !first || !last || !pass || !confirmPass) {
      return 'Email, first name, last name, password and confirm password are required.';
    }
    if (!NAME_RE.test(first) || !NAME_RE.test(last)) {
      return 'First and last name can only include letters (A-Z).';
    }
    if (pass.length < 8) return 'Password must be at least 8 characters.';
    if (/\s/.test(pass)) return 'Password must not contain spaces.';
    if (!/[A-Z]/.test(pass)) return 'Password must include at least one uppercase letter.';
    if (!/[a-z]/.test(pass)) return 'Password must include at least one lowercase letter.';
    if (!/\d/.test(pass)) return 'Password must include at least one number.';
    if (!/[^A-Za-z0-9]/.test(pass)) return 'Password must include at least one special character.';
    if (pass !== confirmPass) return 'Password and confirm password must match.';
    return null;
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = email.trim();
    const normalizedFirstName = toTitle(firstName);
    const normalizedLastName = toTitle(lastName);
    const fullName = `${normalizedFirstName} ${normalizedLastName}`.trim();
    const trimmedPassword = password.trim();
    const validationError = validateCreateForm(
      trimmedEmail,
      normalizedFirstName,
      normalizedLastName,
      trimmedPassword,
      confirmPassword,
    );
    if (validationError) {
      setCreateError(validationError);
      toast(validationError);
      return;
    }
    setCreateError('');
    setFirstName(normalizedFirstName);
    setLastName(normalizedLastName);
    const ok = await addAgent(trimmedEmail, fullName, trimmedPassword);
    if (!ok) {
      toast('Failed to create agent. Check backend/API and try again.');
      return;
    }
    setEmail('');
    setFirstName('');
    setLastName('');
    setPassword('');
    setConfirmPassword('');
    setShowCreatePassword(false);
    setShowConfirmPassword(false);
    setCreateError('');
    setShowCreateModal(false);
    requestAnimationFrame(() => toast('Agent created successfully'));
  };

  const handleDeleteClick = (id: string, label: string) => {
    setDeleteAgentConfirm({ id, label });
    toast(`Delete confirmation opened for ${label}`);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteAgentConfirm) return;
    const ok = await removeAgent(deleteAgentConfirm.id);
    requestAnimationFrame(() => {
      toast(ok ? 'Agent deleted successfully' : 'Failed to remove agent');
    });
    setDeleteAgentConfirm(null);
  };

  const handleDownloadAgentReport = async () => {
    if (!selectedAgent) return;
    setAgentReportDownloading(true);
    try {
      const dayData = filterByMonth(visibleAttendanceDayData, agentReportYear, agentReportMonth - 1);
      if (dayData.length === 0) {
        toast('No attendance data for selected month.');
        return;
      }
      const periodLabel = new Date(agentReportYear, agentReportMonth - 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
      await buildSingleAgentPdf({
        agent: { id: selectedAgent.id, name: selectedAgent.name, email: selectedAgent.email },
        dayData,
        periodLabel,
      });
      requestAnimationFrame(() => toast('Attendance report downloaded'));
    } catch (e) {
      toast('Failed to generate report');
    } finally {
      setAgentReportDownloading(false);
    }
  };

  const width = listCollapsed ? 64 : 280;

  return (
    <div className="flex h-full">
      <div
        className="flex flex-col h-full border-r border-border bg-white shrink-0 transition-[width] duration-200"
        style={{ width }}
      >
        <div
          className={`flex items-center ${
            listCollapsed ? 'justify-center py-3' : 'justify-between px-3 py-2 h-[56px]'
          } border-b border-border`}
        >
          {listCollapsed ? (
            <button
              type="button"
              onClick={() => setListCollapsed(false)}
              className="p-2 rounded-lg text-text-secondary hover:bg-panel hover:text-text-primary transition-colors"
              aria-label="Expand agents list"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setListCollapsed(true)}
                  className="p-2 rounded-lg text-text-secondary hover:bg-panel hover:text-text-primary transition-colors"
                  aria-label="Collapse agents list"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                    Agents
                  </p>
                  <p className="text-[11px] text-text-secondary">
                    {agents.length} account{agents.length === 1 ? '' : 's'}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center justify-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors"
                aria-label="Add agent"
              >
                <UserPlus className="w-4 h-4" />
                <span>Add</span>
              </button>
            </>
          )}
        </div>

        {!listCollapsed && (
          <div className="flex-1 overflow-y-auto">
            {agents.length === 0 ? (
              <p className="px-4 py-6 text-xs text-text-muted">
                No agents yet. Click “Add” to create an account.
              </p>
            ) : (
              <ul className="p-2 space-y-0.5">
                {agents.map((agent) => {
                  const isActive = agent.id === selectedId;
                  return (
                    <li
                      key={agent.id}
                      className={`rounded-lg ${isActive ? 'bg-primary/5' : ''}`}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedId(agent.id)}
                        className={`flex items-center gap-3 px-3 py-2 rounded-lg w-full min-w-0 text-left transition-colors ${
                          isActive
                            ? 'text-primary'
                            : 'text-text-secondary hover:bg-panel hover:text-text-primary'
                        }`}
                      >
                        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold flex-shrink-0">
                          {agent.name.charAt(0)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium truncate">{agent.name}</p>
                          <p className="text-[11px] text-text-muted truncate">
                            {agent.email}
                          </p>
                          <p className="text-[10px] text-text-muted truncate font-mono">
                            ID: {agent.id}
                          </p>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0 flex flex-col p-6">
        <div className="mb-4">
          <h1 className="text-2xl font-bold text-text-primary">Agent Accounts</h1>
          <p className="text-text-secondary mt-1 text-sm">
            Create, inspect, and revoke access for support agents. Each agent gets their own login
            into the agent portal.
          </p>
        </div>

        {selectedAgent ? (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Row 1: Agent info (col 1-2) + Access & Lifecycle (col 3-4) */}
            <div className="lg:col-span-2 bg-card rounded-xl border border-border shadow-sm p-6 space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary text-lg font-semibold">
                  {(editingName ? nameDraft : selectedAgent.name).charAt(0) || '?'}
                </div>
                <div className="min-w-0 flex-1">
                  {editingName ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={nameDraft}
                        onChange={(e) => setNameDraft(e.target.value)}
                        className="flex-1 min-w-0 px-2 py-1.5 text-sm font-semibold border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary text-text-primary"
                        placeholder="Agent name"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const v = nameDraft.trim();
                            if (v) {
                              const parts = v.split(' ').filter(Boolean);
                              if (parts.length !== 2 || !parts.every((p) => NAME_RE.test(p))) {
                                toast('Name must include first and last name using letters only.');
                                return;
                              }
                              const normalized = `${toTitle(parts[0])} ${toTitle(parts[1])}`;
                              void updateAgent(selectedAgent.id, { name: normalized }).then((ok) => {
                                toast(ok ? 'Agent name updated' : 'Failed to update agent name');
                              });
                              setNameDraft(normalized);
                              setEditingName(false);
                            }
                          }
                          if (e.key === 'Escape') {
                            setNameDraft(selectedAgent.name);
                            setEditingName(false);
                          }
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const v = nameDraft.trim();
                          if (v) {
                            const parts = v.split(' ').filter(Boolean);
                            if (parts.length !== 2 || !parts.every((p) => NAME_RE.test(p))) {
                              toast('Name must include first and last name using letters only.');
                              return;
                            }
                            const normalized = `${toTitle(parts[0])} ${toTitle(parts[1])}`;
                            void updateAgent(selectedAgent.id, { name: normalized }).then((ok) => {
                              toast(ok ? 'Agent name updated' : 'Failed to update agent name');
                            });
                            setNameDraft(normalized);
                            setEditingName(false);
                          }
                        }}
                        className="p-1.5 rounded-lg bg-primary text-white hover:bg-primary-dark"
                        aria-label="Save name"
                      >
                        <Check className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setNameDraft(selectedAgent.name);
                          setEditingName(false);
                        }}
                        className="p-1.5 rounded-lg border border-border text-text-muted hover:bg-panel"
                        aria-label="Cancel"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-text-primary">
                        {selectedAgent.name}
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setNameDraft(selectedAgent.name);
                          setEditingName(true);
                        }}
                        className="p-1 rounded-lg text-text-muted hover:bg-panel hover:text-primary transition-colors"
                        aria-label="Rename agent"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                  <p className="text-xs text-text-secondary mt-0.5">Agent login identity</p>
                </div>
              </div>
              <div className="space-y-3 text-sm">
                <div>
                  <p className="text-xs text-text-muted mb-0.5">Agent ID</p>
                  <div className="inline-flex items-center gap-2 px-2 py-1.5 rounded border border-border bg-panel">
                    <code className="text-xs font-mono text-text-primary">{selectedAgent.id}</code>
                    <button
                      type="button"
                      onClick={() => {
                        if (navigator.clipboard?.writeText) {
                          navigator.clipboard.writeText(selectedAgent.id)
                            .then(() => toast('Agent ID copied'))
                            .catch(() => toast('Failed to copy Agent ID'));
                        }
                      }}
                      className="p-1 rounded hover:bg-white text-text-muted"
                      aria-label="Copy agent ID"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <div>
                  <p className="text-xs text-text-muted mb-0.5">Email</p>
                  <p className="text-text-primary break-all">{selectedAgent.email}</p>
                </div>
                <div>
                  <p className="text-xs text-text-muted mb-0.5">Password</p>
                  <div className="flex w-full min-w-0 items-center gap-2 px-3 py-2 rounded border border-border bg-panel">
                    <code className="text-xs font-mono min-w-0 flex-1 truncate">
                      {showPassword
                        ? selectedAgent.password || 'Not available (only shown when set at creation on this browser)'
                        : '••••••••'}
                    </code>
                    <button
                      type="button"
                      disabled={!selectedAgent.password}
                      onClick={() =>
                        setShowPassword((v) => {
                          const next = !v;
                          toast(next ? 'Password shown' : 'Password hidden');
                          return next;
                        })
                      }
                      className="p-1 rounded hover:bg-white text-text-muted disabled:opacity-50 disabled:cursor-not-allowed"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? (
                        <EyeOff className="w-3.5 h-3.5" />
                      ) : (
                        <Eye className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      disabled={!selectedAgent.password}
                      onClick={() => {
                        if (navigator.clipboard?.writeText) {
                          navigator.clipboard.writeText(selectedAgent.password)
                            .then(() => toast('Password copied'))
                            .catch(() => toast('Failed to copy password'));
                        }
                      }}
                      className="p-1 rounded hover:bg-white text-text-muted disabled:opacity-50 disabled:cursor-not-allowed"
                      aria-label="Copy password"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="mt-1 text-[11px] text-text-muted">
                    Share these credentials securely with the agent so they can log into the agent
                    portal.
                  </p>
                </div>
              </div>
            </div>

            {/* Access & Lifecycle - same row as agent info */}
            <div className="lg:col-span-2 bg-card rounded-xl border border-border shadow-sm p-6 space-y-4">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                Access & Lifecycle
              </p>
              <div className="space-y-3 text-xs">
                <p className="text-text-secondary">
                  Deleting this agent will immediately remove their access to the agent portal. It
                  does not delete historical conversations; those stay attached to their name.
                </p>
                <div className="flex flex-wrap gap-2 items-center">
                  <button
                    type="button"
                    onClick={() => handleDeleteClick(selectedAgent.id, selectedAgent.name)}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-status-error/60 text-status-error hover:bg-status-error/10 text-xs font-medium"
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete agent and revoke access
                  </button>
                </div>
                <div className="pt-3 border-t border-border">
                  <p className="text-text-secondary mb-2">Download this agent’s attendance report (PDF) for a month.</p>
                  <div className="flex flex-wrap gap-2 items-center">
                    <select
                      value={agentReportMonth}
                      onChange={(e) => setAgentReportMonth(Number(e.target.value))}
                      className="px-2 py-1.5 border border-border rounded-lg text-xs bg-white focus:outline-none focus:ring-2 focus:ring-primary"
                    >
                      {MONTHS.map((m, i) => (
                        <option key={m} value={i + 1}>{m}</option>
                      ))}
                    </select>
                    <input
                      type="number"
                      min={2020}
                      max={2030}
                      value={agentReportYear}
                      onChange={(e) => setAgentReportYear(Number(e.target.value))}
                      className="px-2 py-1.5 border border-border rounded-lg text-xs w-20 focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                    <button
                      type="button"
                      onClick={handleDownloadAgentReport}
                      disabled={agentReportDownloading}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                      {agentReportDownloading ? 'Generating…' : 'Download report'}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Row 2: Attendance (3/4) + Performance (1/4) */}
            {selectedAgent && (
              <div className="lg:col-span-3 bg-card rounded-xl border border-border shadow-sm p-6 space-y-4 flex flex-col min-h-0">
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                    Attendance
                  </p>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-text-muted">
                    <span>Hours worked:</span>
                    <span className="flex items-center gap-1"><span className="rounded-sm w-3 h-3 bg-[#ebedf0]" /> None</span>
                    <span className="flex items-center gap-1"><span className="rounded-sm w-3 h-3 bg-red-200" /> &lt;2h</span>
                    <span className="flex items-center gap-1"><span className="rounded-sm w-3 h-3 bg-red-300" /> 2–4h</span>
                    <span className="flex items-center gap-1"><span className="rounded-sm w-3 h-3 bg-red-500" /> 4–6h</span>
                    <span className="flex items-center gap-1"><span className="rounded-sm w-3 h-3 bg-red-700" /> 6h+</span>
                    <span className="flex items-center gap-1"><span className="rounded-sm w-3 h-3 bg-[#ebedf0] opacity-70" /> Off day</span>
                  </div>
                </div>
                <div className="flex-1 min-h-0 min-w-0 flex flex-col">
                  <AgentActivityBar agentId={selectedAgent.id} workingDays={schedule.workingDays} dayData={visibleAttendanceDayData} />
                </div>
              </div>
            )}
            {selectedAgent && (
              <div className="lg:col-span-1 bg-card rounded-xl border border-border shadow-sm p-6 space-y-4">
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wider flex items-center gap-2">
                  <TrendingUp className="w-4 h-4" />
                  Performance
                </p>
                <div className="space-y-4">
                  <div className="flex items-center gap-3 p-3 rounded-lg border border-border bg-panel">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                      <Clock className="w-5 h-5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-text-muted">Uptime</p>
                      <p className="text-lg font-semibold text-text-primary">
                        {performanceMetrics.uptimePercent}%
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-lg border border-border bg-panel">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                      <TrendingUp className="w-5 h-5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-text-muted">Avg response</p>
                      <p className="text-lg font-semibold text-text-primary">
                        {formatAvgResponse(performanceMetrics.avgResponseTimeSeconds)}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-sm">
              <p className="text-sm font-medium text-text-primary mb-1">
                No agent selected
              </p>
              <p className="text-xs text-text-secondary mb-3">
                Choose an agent from the agents bar on the left to see their login details and
                access controls.
              </p>
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark"
              >
                <UserPlus className="w-4 h-4" />
                Create first agent
              </button>
            </div>
          </div>
        )}
      </div>

      {deleteAgentConfirm && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/40"
          onClick={() => setDeleteAgentConfirm(null)}
        >
          <div
            className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm font-semibold text-text-primary mb-1">Delete agent</p>
            <p className="text-xs text-text-secondary mb-6">
              Delete &quot;{deleteAgentConfirm.label}&quot; and remove their access to the agent portal? This does not delete historical conversations.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                  onClick={() => {
                    setDeleteAgentConfirm(null);
                    toast('Delete cancelled');
                  }}
                className="px-4 py-2 rounded-lg border border-border text-xs font-medium text-text-primary hover:bg-panel"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteConfirm}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-status-error text-white text-xs font-medium hover:opacity-90"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Delete agent
              </button>
            </div>
          </div>
        </div>
      )}

      {showCreateModal && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/40"
          onClick={() => setShowCreateModal(false)}
        >
          <div
            className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4">
              <p className="text-sm font-semibold text-text-primary">Create agent account</p>
              <p className="text-xs text-text-secondary mt-1">
                Set email, first name, last name, and initial password. A unique agent ID will be
                generated by the system. Share the credentials with the agent to give them access to
                the agent portal.
              </p>
            </div>
            <form onSubmit={handleCreate} className="space-y-3 text-sm">
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="agent@example.com"
                  className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  First name
                </label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => {
                    setCreateError('');
                    setFirstName(e.target.value.replace(/\s+/g, ''));
                  }}
                  onBlur={() => setFirstName((prev) => toTitle(prev))}
                  placeholder="First name"
                  className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Last name
                </label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => {
                    setCreateError('');
                    setLastName(e.target.value.replace(/\s+/g, ''));
                  }}
                  onBlur={() => setLastName((prev) => toTitle(prev))}
                  placeholder="Last name"
                  className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Password
                </label>
                <div className="flex w-full min-w-0 items-center gap-2 px-3 py-2 rounded border border-border bg-white">
                  <input
                    type={showCreatePassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => {
                      setCreateError('');
                      setPassword(e.target.value);
                    }}
                    placeholder="Set initial password"
                    className="flex-1 min-w-0 bg-transparent focus:outline-none text-sm"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowCreatePassword((v) => !v)}
                    className="p-1 rounded hover:bg-panel text-text-muted"
                    aria-label={showCreatePassword ? 'Hide password' : 'Show password'}
                  >
                    {showCreatePassword ? (
                      <EyeOff className="w-3.5 h-3.5" />
                    ) : (
                      <Eye className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-text-muted">
                  Min 8 chars, including uppercase, lowercase, number, and special character.
                </p>
              </div>
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">
                  Confirm password
                </label>
                <div className="flex w-full min-w-0 items-center gap-2 px-3 py-2 rounded border border-border bg-white">
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(e) => {
                      setCreateError('');
                      setConfirmPassword(e.target.value);
                    }}
                    placeholder="Confirm initial password"
                    className="flex-1 min-w-0 bg-transparent focus:outline-none text-sm"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((v) => !v)}
                    className="p-1 rounded hover:bg-panel text-text-muted"
                    aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                  >
                    {showConfirmPassword ? (
                      <EyeOff className="w-3.5 h-3.5" />
                    ) : (
                      <Eye className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </div>
              {createError ? (
                <p className="text-xs text-status-error">{createError}</p>
              ) : null}
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false);
                    setCreateError('');
                    toast('Create agent cancelled');
                  }}
                  className="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary hover:bg-panel"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 px-4 py-1.5 bg-primary text-white rounded-lg text-xs font-medium hover:bg-primary-dark"
                >
                  <UserPlus className="w-4 h-4" />
                  Create agent
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
