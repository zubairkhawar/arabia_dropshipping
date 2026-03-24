'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ChevronLeft, UserPlus, UserMinus, ArrowRightLeft } from 'lucide-react';
import { useTeams } from '@/contexts/TeamsContext';
import { useAgents } from '@/contexts/AgentsContext';
import { useToast } from '@/contexts/ToastContext';

export default function AdminTeamManagePage() {
  const params = useParams();
  const teamId = (params?.teamId as string) || '';
  const { teams, getTeam, addMemberToTeam, removeMemberFromTeam, transferMember } = useTeams();
  const { agents } = useAgents();
  const { toast } = useToast();
  const team = getTeam(teamId);
  const otherTeams = teams.filter((t) => t.id !== teamId);

  const [newMemberId, setNewMemberId] = useState('');
  const [transferTarget, setTransferTarget] = useState<Record<string, string>>({});

  const availableAgentsToAdd = team
    ? agents.filter((a) => !team.members.some((member) => member.agentId === a.id))
    : [];

  if (!team) {
    return (
      <div className="space-y-6">
        <Link href="/admin/agents" className="inline-flex items-center gap-2 text-sm text-primary hover:underline">
          <ChevronLeft className="w-4 h-4" />
          Back
        </Link>
        <p className="text-text-secondary">Team not found.</p>
      </div>
    );
  }

  const handleAddMember = async () => {
    if (!newMemberId) return;
    const ok = await addMemberToTeam(teamId, newMemberId);
    if (!ok) {
      toast('Failed to add member');
      return;
    }
    setNewMemberId('');
    toast('Member added');
  };

  const handleRemove = async (memberName: string, memberAgentId: string) => {
    if (confirm(`Remove ${memberName} from ${team.name}?`)) {
      const ok = await removeMemberFromTeam(teamId, memberAgentId);
      if (!ok) {
        toast('Failed to remove member');
        return;
      }
      toast('Member removed');
    }
  };

  const handleTransfer = async (memberName: string, memberAgentId: string) => {
    const toId = transferTarget[memberAgentId];
    if (!toId) return;
    const ok = await transferMember(teamId, memberAgentId, toId);
    if (!ok) {
      toast('Failed to transfer member');
      return;
    }
    setTransferTarget((prev) => ({ ...prev, [memberAgentId]: '' }));
    toast('Member transferred');
  };

  return (
    <div className="space-y-6">
      <div>
        <Link href="/admin/teams" className="inline-flex items-center gap-2 text-sm text-primary hover:underline mb-2">
          <ChevronLeft className="w-4 h-4" />
          Back to Teams
        </Link>
        <h1 className="text-2xl font-bold text-text-primary">{team.name}</h1>
        <p className="text-text-secondary mt-1">Manage members. Changes appear as soft messages in the team channel chat.</p>
      </div>

      <div className="bg-card rounded-xl border border-border shadow-sm p-6 max-w-2xl">
        <h2 className="font-semibold text-text-primary mb-4">Add member</h2>
        <p className="text-sm text-text-muted mb-2">Members can be added from the admin panel only. They will see a soft message in the team channel.</p>
        <div className="flex gap-2">
          <select
            value={newMemberId}
            onChange={(e) => setNewMemberId(e.target.value)}
            className="flex-1 px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-text-primary bg-white"
          >
            <option value="">Select agent</option>
            {availableAgentsToAdd.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name} ({agent.email})
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleAddMember}
            disabled={!newMemberId}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors"
          >
            <UserPlus className="w-4 h-4" />
            Add
          </button>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-border shadow-sm p-6 max-w-2xl">
        <h2 className="font-semibold text-text-primary mb-4">Members ({team.members.length})</h2>
        {team.members.length === 0 ? (
          <p className="text-text-muted text-sm">No members yet. Add one above.</p>
        ) : (
          <ul className="space-y-3">
            {team.members.map((member) => (
              <li
                key={member.agentId}
                className="flex items-center justify-between gap-4 py-3 px-4 rounded-lg bg-panel border border-border"
              >
                <span className="font-medium text-text-primary">{member.name}</span>
                <div className="flex items-center gap-2 flex-wrap">
                  {otherTeams.length > 0 && (
                    <>
                      <select
                        value={transferTarget[member.agentId] ?? ''}
                        onChange={(e) =>
                          setTransferTarget((prev) => ({ ...prev, [member.agentId]: e.target.value }))
                        }
                        className="px-3 py-1.5 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                      >
                        <option value="">Transfer to...</option>
                        {otherTeams.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => void handleTransfer(member.name, member.agentId)}
                        disabled={!transferTarget[member.agentId]}
                        className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-border hover:bg-panel disabled:opacity-50 disabled:cursor-not-allowed text-text-secondary"
                        title="Transfer to another team"
                      >
                        <ArrowRightLeft className="w-4 h-4" />
                        Transfer
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleRemove(member.name, member.agentId)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-status-error/50 text-status-error hover:bg-status-error/10"
                    title="Remove from team"
                  >
                    <UserMinus className="w-4 h-4" />
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
