'use client';

import { useState, useEffect, useLayoutEffect, useRef, useCallback, type ReactNode } from 'react';
import { useTeamChannelRealtime, type TeamChannelWsEvent } from '@/hooks/useTeamChannelRealtime';
import { useDmConversationRealtime, type DmWsEvent } from '@/hooks/useDmConversationRealtime';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Bot,
  AlertCircle,
  Users,
  User,
  ChevronRight,
  Info,
  Image as ImageIcon,
  FileText,
  Link2,
  Star,
  X,
  CornerDownLeft,
  Smile,
  Check,
  Copy,
  Trash2,
  ChevronDown,
  Plus,
  Mic,
  Square,
  Play,
  Pause,
  UserPlus,
  Pencil,
  Search,
} from 'lucide-react';
import { useAgentProfile } from '@/contexts/AgentProfileContext';
import { useInboxConversations } from '@/contexts/InboxConversationsContext';
import type { InboxMessage } from '@/contexts/InboxConversationsContext';
import type { TeamEvent } from '@/contexts/TeamsContext';
import { useTeams } from '@/contexts/TeamsContext';
import { useAgents } from '@/contexts/AgentsContext';
import { useNotifications } from '@/contexts/NotificationsContext';
import { useDmChats } from '@/contexts/DmChatsContext';

interface MessageAttachment {
  type: 'file' | 'photo' | 'voice';
  name: string;
  url: string;
  durationSeconds?: number;
}

interface MessageReaction {
  emoji: string;
  userId: string;
  userName: string;
  reactedAt: string;
}

interface Message {
  id: number;
  content: string;
  sender: 'customer' | 'agent' | 'ai';
  senderName: string;
  senderAgentId?: number;
  /** Admin team channel: message posted from /admin/teams (right-aligned for admin viewer). */
  postedByAdmin?: boolean;
  timestamp: string;
  /** ISO date string for actual time and date grouping */
  sentAt?: string;
  reactions?: MessageReaction[];
  replyTo?: { id: number; senderName: string; content: string };
  attachment?: MessageAttachment;
  /** Team channel: DB team_id for this row; PATCH reactions must use this URL, not the viewer's selected team (avoids 404 after switching teams). */
  channelTeamId?: number;
  /** Parsed from team JSON payload: agent ids @mentioned in this message. */
  mentionAgentIds?: number[];
  replyToMessageId?: number;
  editedAt?: string;
  deletedForEveryone?: boolean;
  messageStatus?: { sent: boolean; delivered: boolean; read: boolean };
  /** Team channel: server receipt aggregate for outgoing messages (sender/admin view). */
  teamReceiptSummary?: { recipient_count: number; delivered_count: number; read_count: number };
  sendFailed?: boolean;
}

type ThreadMessageEdit =
  | { source: 'inbox'; id: number; text: string }
  | { source: 'dm'; id: number; text: string }
  | { source: 'team'; id: number; text: string };

interface TeamChannelMessageRow {
  id: number;
  team_id: number;
  sender_agent_id: number | null;
  posted_by_admin?: boolean;
  sender_name: string;
  content: string;
  created_at: string;
  reply_to_message_id?: number | null;
  edited_at?: string | null;
  deleted_for_everyone_at?: string | null;
  receipt_summary?: {
    recipient_count: number;
    delivered_count: number;
    read_count: number;
  } | null;
}

interface TeamChannelPayload {
  text?: string;
  attachment?: MessageAttachment;
  replyTo?: { id: number; senderName: string; content: string };
  reactions?: MessageReaction[];
  /** Agent ids @mentioned (stored in JSON payload). */
  mentions?: number[];
}

const WA_NAME_COLORS = [
  'text-orange-700',
  'text-teal-600',
  'text-rose-600',
  'text-violet-600',
  'text-amber-800',
  'text-cyan-700',
  'text-emerald-700',
] as const;

function whatsappSenderNameClass(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i += 1) h = (h * 31 + name.charCodeAt(i)) | 0;
  return WA_NAME_COLORS[Math.abs(h) % WA_NAME_COLORS.length];
}

const isHeicLikeAttachment = (attachment?: MessageAttachment) => {
  if (!attachment) return false;
  const n = attachment.name.toLowerCase();
  return n.endsWith('.heic') || n.endsWith('.heif');
};

const TEAM_REACTION_CACHE_PREFIX = 'team-reaction-cache:';

export interface ChatWindowProps {
  isInternalChat?: boolean;
  title?: string;
  subtitle?: string;
  showTransferControls?: boolean;
  teamId?: string;
  /** For team channel: e.g. "Team A". Shown next to "# Team Channel" in header. */
  teamName?: string;
  /** For team channel: names shown in header subtitle, e.g. "Ali, Hamza, Sarah". */
  teamMemberNames?: string[];
  /** For team channel: roster with agent ids (mentions + read receipts). */
  teamMemberRoster?: Array<{ agentId: string; name: string }>;
  /** For team channel: soft system messages (member added/removed/transferred). */
  teamEvents?: TeamEvent[];
  /** When true, chat is read-only (monitor mode: no replies/reactions/menus). */
  readOnly?: boolean;
  /** When true, show broadcast input so admin can send messages and tag agents with @. */
  broadcastMode?: boolean;
}

const defaultCustomerMessages: Message[] = [
  {
    id: 1,
    content: 'Hello! How can I help you today?',
    sender: 'ai',
    senderName: 'AI Assistant',
    timestamp: '2:24 PM',
    sentAt: new Date(Date.now() - 86400 * 1000).toISOString(),
  },
  {
    id: 2,
    content: 'I need help with my order #12345',
    sender: 'customer',
    senderName: 'Ahmed Ali',
    timestamp: '2:25 PM',
    sentAt: new Date(Date.now() - 86400 * 1000 + 60000).toISOString(),
  },
  {
    id: 3,
    content: 'I can help you with that. Let me check your order status.',
    sender: 'ai',
    senderName: 'AI Assistant',
    timestamp: '2:26 PM',
    sentAt: new Date(Date.now() - 86400 * 1000 + 120000).toISOString(),
  },
  {
    id: 4,
    content:
      'Your order is currently in transit and will be delivered within 2-3 business days.',
    sender: 'ai',
    senderName: 'AI Assistant',
    timestamp: '2:27 PM',
    sentAt: new Date(Date.now() - 86400 * 1000 + 180000).toISOString(),
  },
];

const defaultInternalMessages: Message[] = [
  {
    id: 1,
    content: 'Hey team, customer on order #12345 is asking about delivery ETA.',
    sender: 'agent',
    senderName: 'You',
    timestamp: new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
    sentAt: new Date().toISOString(),
  },
  {
    id: 2,
    content: "I'll keep an eye on logistics updates for this one.",
    sender: 'agent',
    senderName: 'Hamza',
    timestamp: new Date(Date.now() - 60000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
    sentAt: new Date(Date.now() - 60000).toISOString(),
    reactions: [
      { emoji: '👍', userId: 'hamza', userName: 'Hamza', reactedAt: new Date(Date.now() - 120000).toISOString() },
      { emoji: '❤️', userId: 'sarah', userName: 'Sarah', reactedAt: new Date(Date.now() - 60000).toISOString() },
      { emoji: '❤️', userId: 'ali', userName: 'Ali', reactedAt: new Date(Date.now() - 30000).toISOString() },
    ],
  },
  {
    id: 3,
    content: 'If it escalates, feel free to transfer to me.',
    sender: 'agent',
    senderName: 'Sarah',
    timestamp: new Date(Date.now() - 120000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
    sentAt: new Date(Date.now() - 120000).toISOString(),
  },
];

const internalTeamMembers = [
  { id: 'ali', name: 'Ali' },
  { id: 'sarah', name: 'Sarah' },
  { id: 'hamza', name: 'Hamza' },
];

export function ChatWindow({
  isInternalChat = false,
  title = 'Ahmed Ali',
  subtitle = 'Store: My Shopify Store',
  showTransferControls = false,
  teamId,
  teamName,
  teamMemberNames = [],
  teamMemberRoster = [],
  teamEvents = [],
  readOnly = false,
  broadcastMode = false,
}: ChatWindowProps) {
  const pathname = usePathname();
  const { avatarUrl: agentAvatarUrl, fullName: agentFullName } = useAgentProfile();
  const inboxConv = useInboxConversations();
  const { teams } = useTeams();
  const { agents, getCurrentAgent } = useAgents();
  const notifications = useNotifications();
  const {
    getMessagesBySlug,
    loadInitialDmThread,
    loadOlderDmMessages,
    mergeIncomingDmMessage,
    patchDmMessage,
    dmHasMoreOlder,
    sendMessageBySlug,
    loadingDmSlug,
    loadingOlderDmSlug,
    getConversationBySlug,
    reportDmUnread,
    clearDmUnread,
  } = useDmChats();
  const API_BASE =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    'https://arabia-dropshipping.onrender.com';
  const TENANT_ID = 1;
  /** Admin team posts require Bearer token (role=admin). Agents may send token too; server only enforces it for posted_by_admin. */
  const teamChannelJsonHeaders = (): Record<string, string> => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (typeof window !== 'undefined') {
      const t = localStorage.getItem('auth_token');
      if (t) h.Authorization = `Bearer ${t}`;
    }
    return h;
  };
  const encodeTeamMessageContent = (payload: TeamChannelPayload) =>
    `__TEAM_MSG_JSON__${JSON.stringify(payload)}`;
  const decodeTeamMessageContent = (raw: string): TeamChannelPayload => {
    if (!raw.startsWith('__TEAM_MSG_JSON__')) return { text: raw };
    try {
      return JSON.parse(raw.replace('__TEAM_MSG_JSON__', '')) as TeamChannelPayload;
    } catch {
      return { text: raw };
    }
  };

  const DM_MSG_PREFIX = '__DM_MSG_JSON__';
  const encodeDmMessagePayload = (payload: { text: string; attachment?: MessageAttachment }) =>
    `${DM_MSG_PREFIX}${JSON.stringify({ v: 1, text: payload.text, attachment: payload.attachment })}`;
  const decodeDmMessageContent = (raw: string): { text: string; attachment?: MessageAttachment } => {
    if (!raw.startsWith(DM_MSG_PREFIX)) return { text: raw };
    try {
      const o = JSON.parse(raw.slice(DM_MSG_PREFIX.length)) as {
        v?: number;
        text?: string;
        attachment?: MessageAttachment;
      };
      if (o && typeof o.text === 'string') {
        return { text: o.text, attachment: o.attachment };
      }
    } catch {
      // ignore
    }
    return { text: raw };
  };

  async function blobUrlToDataUrl(blobUrl: string): Promise<string> {
    const res = await fetch(blobUrl);
    const blob = await res.blob();
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result));
      fr.onerror = () => reject(new Error('read failed'));
      fr.readAsDataURL(blob);
    });
  }

  const transferTargetOptions = (() => {
    const currentName = agentFullName || getCurrentAgent()?.name || '';
    const team = teams.find((t) => t.members.some((m) => m.name === currentName));
    if (!team) return [];
    const otherNames = team.members
      .map((m) => m.name)
      .filter((m) => m !== currentName);
    return otherNames
      .map((name) => {
        const agent = agents.find((a) => a.name === name);
        return agent ? { id: agent.id, name: agent.name } : null;
      })
      .filter((a): a is { id: string; name: string } => a != null);
  })();
  const isTeamChannel = pathname?.startsWith('/agent/team') || (pathname?.startsWith('/admin/teams') && !!teamName);
  const isDmPage = pathname?.startsWith('/agent/dm');
  const dmSlug = isDmPage ? (pathname.replace('/agent/dm/', '').split('/')[0] || null) : null;
  const isInboxPage = pathname?.startsWith('/agent/inbox') || pathname?.startsWith('/admin/inbox');
  const showBroadcastInput = broadcastMode && isInternalChat && !!teamName;

  const [messages, setMessages] = useState<Message[]>(() => {
    if (isInboxPage && !isInternalChat) {
      return [];
    }
    if (isInternalChat && isDmPage) {
      return [];
    }
    if (isInternalChat && isTeamChannel) {
      return [];
    }
    return isInternalChat ? defaultInternalMessages : defaultCustomerMessages;
  });

  const selectedConv =
    inboxConv?.selectedId != null
      ? inboxConv.conversations.find((c) => c.id === inboxConv.selectedId)
      : undefined;
  const isInboxWithSelection = !!inboxConv && inboxConv.selectedId != null;
  const inboxMessageCount =
    isInboxWithSelection && inboxConv?.selectedId != null
      ? inboxConv.getMessages(inboxConv.selectedId).length
      : 0;
  const hasSelectedConversation = !!selectedConv;
  const headerTitle = isTeamChannel && teamName
    ? `# Team Channel • ${teamName}`
    : isInboxPage
      ? (selectedConv?.customerName || 'No conversation selected')
      : title;
  const headerSubtitle = isTeamChannel && teamMemberNames.length > 0
    ? teamMemberNames.join(', ')
    : isInboxPage
      ? (selectedConv ? `Conversation ${selectedConv.customerId}` : 'Select a conversation to begin monitoring.')
      : subtitle;

  useEffect(() => {
    if (!isInboxWithSelection || isInternalChat) return;
    const convId = inboxConv!.selectedId!;
    const stored = inboxConv.getMessages(convId);
    setMessages((prev) => {
      const prevById = new Map(prev.map((m) => [m.id, m]));
      return stored.map(
        (im): Message => ({
          id: im.id,
          content: im.content,
          sender: im.sender,
          senderName: im.senderName,
          timestamp: im.timestamp,
          sentAt: im.sentAt,
          replyTo: im.replyTo,
          replyToMessageId: im.replyToMessageId,
          editedAt: im.editedAt,
          deletedForEveryone: im.deletedForEveryone,
          messageStatus: im.messageStatus,
          sendFailed: im.sendFailed,
          reactions: prevById.get(im.id)?.reactions,
        }),
      );
    });
  }, [isInboxWithSelection, isInternalChat, inboxConv?.selectedId, inboxMessageCount]);

  useEffect(() => {
    if (!isInboxPage || isInternalChat || inboxConv?.selectedId == null) return;
    const msgs = inboxConv.getMessages(inboxConv.selectedId);
    if (msgs.length < inboxLastLenRef.current) {
      inboxLastLenRef.current = msgs.length;
      return;
    }
    if (msgs.length > inboxLastLenRef.current) {
      const added = msgs.slice(inboxLastLenRef.current);
      inboxLastLenRef.current = msgs.length;
      const last = added[added.length - 1];
      if (last && (last.sender === 'customer' || last.sender === 'ai') && !inboxNearBottomRef.current) {
        setInboxNewBelowOpen(true);
      }
    }
  }, [isInboxPage, isInternalChat, inboxConv, inboxMessageCount]);

  const dmThreadSlugRef = useRef<string | null>(null);

  useEffect(() => {
    if (!isInternalChat || !isDmPage || !dmSlug) return;
    void loadInitialDmThread(dmSlug);
  }, [isInternalChat, isDmPage, dmSlug, loadInitialDmThread]);

  useEffect(() => {
    if (!isInternalChat || !isDmPage || !dmSlug) return;
    const rows = getMessagesBySlug(dmSlug);
    const slugChanged = dmThreadSlugRef.current !== dmSlug;
    dmThreadSlugRef.current = dmSlug;

    if (rows.length === 0) {
      if (slugChanged) setMessages([]);
      return;
    }

    const byId = new Map(rows.map((r) => [r.id, r]));
    const mapped: Message[] = rows.map((m) => {
      const parsed = decodeDmMessageContent(m.content);
      const parent =
        m.replyToMessageId != null ? byId.get(m.replyToMessageId) : undefined;
      const parentParsed =
        parent != null ? decodeDmMessageContent(parent.content) : { text: '', attachment: undefined };
      const outgoingDm = m.senderName === 'You';
      return {
        id: m.id,
        content: parsed.text || (parsed.attachment ? '' : m.content),
        sender: 'agent' as const,
        senderName: m.senderName,
        senderAgentId: Number.parseInt(m.senderAgentId, 10) || undefined,
        timestamp: new Date(m.createdAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
        sentAt: m.createdAt,
        replyToMessageId: m.replyToMessageId,
        replyTo:
          parent != null
            ? {
                id: parent.id,
                senderName: parent.senderName,
                content:
                  parentParsed.text ||
                  (parentParsed.attachment?.type === 'voice' ? 'Voice message' : parent.content),
              }
            : undefined,
        editedAt: m.editedAt,
        deletedForEveryone: m.deletedForEveryone,
        attachment: parsed.attachment,
        messageStatus: outgoingDm
          ? {
              sent: true,
              delivered: Boolean(m.peerDeliveredAt),
              read: Boolean(m.peerReadAt),
            }
          : undefined,
      };
    });
    setMessages(mapped);
  }, [isInternalChat, isDmPage, dmSlug, getMessagesBySlug]);

  const [inputValue, setInputValue] = useState('');
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [showGroupInfo, setShowGroupInfo] = useState(false);
  const [showAgentProfile, setShowAgentProfile] = useState(false);
  const [activeGroupTab, setActiveGroupTab] = useState<'info' | 'media' | 'starred' | 'members'>('info');
  const [teamAssets, setTeamAssets] = useState<Array<{
    id: number;
    asset_type: 'image' | 'doc' | 'link';
    title?: string;
    url?: string;
    file_name?: string;
    mime_type?: string;
    size_bytes?: number;
    content_base64?: string;
  }>>([]);
  const [teamAssetsLoading, setTeamAssetsLoading] = useState(false);
  const [assetError, setAssetError] = useState<string | null>(null);
  const [showAddLink, setShowAddLink] = useState(false);
  const [linkTitle, setLinkTitle] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const [previewImageSrc, setPreviewImageSrc] = useState<string | null>(null);
  const [starredIds, setStarredIds] = useState<number[]>([]);
  const [activeMessageMenuId, setActiveMessageMenuId] = useState<number | null>(null);
  const [activeReactionPickerId, setActiveReactionPickerId] = useState<number | null>(null);
  const [deletedForMeIds, setDeletedForMeIds] = useState<number[]>([]);
  const [replyingTo, setReplyingTo] = useState<{ id: number; senderName: string; content: string } | null>(null);
  const [messageInfoId, setMessageInfoId] = useState<number | null>(null);
  const [reactionDetailMessageId, setReactionDetailMessageId] = useState<number | null>(null);
  const [reactionDetailFilter, setReactionDetailFilter] = useState<'all' | string>('all');
  const [dropdownPlaceAbove, setDropdownPlaceAbove] = useState(true);
  const [showAttachmentMenu, setShowAttachmentMenu] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingElapsedSec, setRecordingElapsedSec] = useState(0);
  const [recordingPaused, setRecordingPaused] = useState(false);
  const [voiceReviewAttachment, setVoiceReviewAttachment] = useState<MessageAttachment | null>(null);
  const [voiceReviewPlaying, setVoiceReviewPlaying] = useState(false);
  const recordingTickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const voiceReviewAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const voiceCaptureCancelledRef = useRef(false);
  const [pendingAttachment, setPendingAttachment] = useState<MessageAttachment | null>(null);
  const [playingVoiceId, setPlayingVoiceId] = useState<number | null>(null);
  const [voiceProgress, setVoiceProgress] = useState<Record<number, number>>({});
  const [showTransferMenu, setShowTransferMenu] = useState(false);
  const [showTransferModal, setShowTransferModal] = useState(false);
  const [transferTargetId, setTransferTargetId] = useState<string | null>(null);
  const [transferTargetName, setTransferTargetName] = useState<string>('');
  const [transferDescription, setTransferDescription] = useState('');
  const recordingChunksRef = useRef<Blob[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingStartRef = useRef<number>(0);
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const voiceMessageIdRef = useRef<number | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const BOTTOM_THRESHOLD_PX = 80;
  const teamNearBottomRef = useRef(true);
  const dmNearBottomRef = useRef(true);
  const inboxNearBottomRef = useRef(true);
  const inboxLastLenRef = useRef(0);
  const lastSyncedInboxReadRef = useRef<{ convId: number; id: number } | null>(null);
  const teamLastSyncIsoRef = useRef<string | null>(null);
  const dmLastSyncIsoRef = useRef<string | null>(null);

  useEffect(() => {
    lastSyncedInboxReadRef.current = null;
    inboxLastLenRef.current = 0;
    setInboxNewBelowOpen(false);
  }, [inboxConv?.selectedId]);
  const initialScrollThreadKeyDoneRef = useRef<string>('');
  const [teamHasMoreOlder, setTeamHasMoreOlder] = useState(false);
  const [inboxLoadingOlder, setInboxLoadingOlder] = useState(false);
  const [teamLoadingOlder, setTeamLoadingOlder] = useState(false);
  const [teamNewBelowOpen, setTeamNewBelowOpen] = useState(false);
  const [dmNewBelowOpen, setDmNewBelowOpen] = useState(false);
  const [inboxNewBelowOpen, setInboxNewBelowOpen] = useState(false);
  const [copyToastVisible, setCopyToastVisible] = useState(false);
  const copyToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [threadSearchOpen, setThreadSearchOpen] = useState(false);
  const [threadSearchQuery, setThreadSearchQuery] = useState('');
  const [threadMessageEdit, setThreadMessageEdit] = useState<ThreadMessageEdit | null>(null);

  useEffect(() => {
    const inThread =
      (isInboxPage && hasSelectedConversation && !isInternalChat) ||
      (isInternalChat && (isTeamChannel || isDmPage));
    const onDocKey = (e: KeyboardEvent) => {
      if (!inThread) return;
      if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
        e.preventDefault();
        setThreadSearchOpen(true);
      }
      if (e.key === 'Escape' && threadSearchOpen) {
        setThreadSearchOpen(false);
        setThreadSearchQuery('');
      }
    };
    window.addEventListener('keydown', onDocKey);
    return () => window.removeEventListener('keydown', onDocKey);
  }, [
    isTeamChannel,
    isDmPage,
    isInboxPage,
    hasSelectedConversation,
    isInternalChat,
    threadSearchOpen,
  ]);

  const [stickyDate, setStickyDate] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [showMentionDropdown, setShowMentionDropdown] = useState(false);
  const refreshTeamAssets = async () => {
    if (!teamId) return;
    setTeamAssetsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/teams/${Number(teamId)}/assets?tenant_id=${TENANT_ID}`);
      if (!res.ok) throw new Error('Failed to load team assets');
      const rows = await res.json();
      setTeamAssets(Array.isArray(rows) ? rows : []);
    } catch (e: any) {
      // Keep panel usable even if backend has no rows/table yet.
      setTeamAssets([]);
      setAssetError(null);
    } finally {
      setTeamAssetsLoading(false);
    }
  };

  useEffect(() => {
    if (!showGroupInfo || activeGroupTab !== 'media' || !teamId) return;
    void refreshTeamAssets();
  }, [showGroupInfo, activeGroupTab, teamId]);

  const handleFileUpload = async (file: File, kind: 'image' | 'doc') => {
    if (!teamId) return;
    const buf = await file.arrayBuffer();
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
    const res = await fetch(`${API_BASE}/api/teams/${Number(teamId)}/assets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: TENANT_ID,
        asset_type: kind,
        title: file.name,
        file_name: file.name,
        mime_type: file.type || undefined,
        content_base64: b64,
        created_by_agent_id: getCurrentAgent()?.id ? Number(getCurrentAgent()!.id) : null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Upload failed');
    }
    await refreshTeamAssets();
  };

  const addLinkAsset = async () => {
    if (!teamId || !linkUrl.trim()) return;
    const res = await fetch(`${API_BASE}/api/teams/${Number(teamId)}/assets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: TENANT_ID,
        asset_type: 'link',
        title: linkTitle.trim() || linkUrl.trim(),
        url: linkUrl.trim(),
        created_by_agent_id: getCurrentAgent()?.id ? Number(getCurrentAgent()!.id) : null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setAssetError(err.detail || 'Failed to save link');
      return;
    }
    setShowAddLink(false);
    setLinkTitle('');
    setLinkUrl('');
    await refreshTeamAssets();
  };
  const [mentionFilter, setMentionFilter] = useState('');
  const mentionAnchorRef = useRef<number>(0);
  const [mentionIndex, setMentionIndex] = useState(0);
  const mentionIdsRef = useRef<Set<number>>(new Set());
  const typingStopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [memberReadStates, setMemberReadStates] = useState<Record<string, number>>({});
  const [teamTypers, setTeamTypers] = useState<Record<string, { name: string; until: number }>>({});
  const [readReceiptOpenId, setReadReceiptOpenId] = useState<number | null>(null);

  type MentionRosterItem = { agentId: string; name: string };
  const mentionRoster: MentionRosterItem[] =
    teamMemberRoster.length > 0
      ? teamMemberRoster
      : teamMemberNames.map((name) => ({ agentId: '', name }));

  const mentionComposerEnabled =
    isTeamChannel &&
    !readOnly &&
    (showBroadcastInput || teamMemberNames.length > 0 || teamMemberRoster.length > 0);

  const DROPDOWN_APPROX_HEIGHT = 320;
  const mentionCandidatesList = mentionRoster.filter((o) =>
    o.name.toLowerCase().includes((mentionFilter || '').toLowerCase()),
  );

  useEffect(() => {
    if (activeMessageMenuId === null) return;
    const el = document.getElementById(`message-${activeMessageMenuId}`);
    if (!el) {
      setDropdownPlaceAbove(true);
      return;
    }
    const rect = el.getBoundingClientRect();
    const spaceAbove = rect.top;
    const spaceBelow = typeof window !== 'undefined' ? window.innerHeight - rect.bottom : 0;
    const placeAbove =
      spaceAbove >= DROPDOWN_APPROX_HEIGHT || spaceBelow < DROPDOWN_APPROX_HEIGHT;
    setDropdownPlaceAbove(placeAbove);
  }, [activeMessageMenuId]);

  const viewerAgentId = Number(getCurrentAgent()?.id || 0);
  const reactionActorId =
    broadcastMode && isTeamChannel ? 'admin-broadcast' : viewerAgentId ? `agent-${viewerAgentId}` : 'me';
  const reactionActorName =
    broadcastMode && isTeamChannel ? 'Admin' : agentFullName || getCurrentAgent()?.name || 'You';
  const getReactionCacheKey = () => (teamId ? `${TEAM_REACTION_CACHE_PREFIX}${teamId}` : null);
  const readReactionCache = (): Record<string, MessageReaction[]> => {
    if (typeof window === 'undefined') return {};
    const key = getReactionCacheKey();
    if (!key) return {};
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return {};
      const parsed = JSON.parse(raw) as Record<string, MessageReaction[]>;
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  };
  const writeReactionCache = (messageId: number, reactions: MessageReaction[] | undefined) => {
    if (typeof window === 'undefined') return;
    const key = getReactionCacheKey();
    if (!key) return;
    const current = readReactionCache();
    if (!reactions || reactions.length === 0) {
      delete current[String(messageId)];
    } else {
      current[String(messageId)] = reactions;
    }
    localStorage.setItem(key, JSON.stringify(current));
  };
  const mergeReactions = (
    serverReactions: MessageReaction[] | undefined,
    cachedReactions: MessageReaction[] | undefined,
  ): MessageReaction[] | undefined => {
    const a = serverReactions ?? [];
    const b = cachedReactions ?? [];
    if (a.length === 0 && b.length === 0) return undefined;
    const byUser = new Map<string, MessageReaction>();
    for (const r of [...a, ...b]) {
      const existing = byUser.get(r.userId);
      if (!existing) {
        byUser.set(r.userId, r);
        continue;
      }
      const existingTs = new Date(existing.reactedAt).getTime();
      const nextTs = new Date(r.reactedAt).getTime();
      if (Number.isFinite(nextTs) && (!Number.isFinite(existingTs) || nextTs >= existingTs)) {
        byUser.set(r.userId, r);
      }
    }
    return Array.from(byUser.values());
  };

  const mapTeamRowToMessage = useCallback(
    (m: TeamChannelMessageRow): Message => {
      const deletedForEveryone = Boolean(m.deleted_for_everyone_at);
      const payload = decodeTeamMessageContent(m.content);
      const cachedReactions = readReactionCache()[String(m.id)];
      const postedByAdmin = !!m.posted_by_admin;
      const senderName = broadcastMode
        ? postedByAdmin
          ? 'Admin'
          : m.sender_name
        : m.sender_agent_id === viewerAgentId
          ? 'You'
          : m.sender_name;
      const mentionIds = payload.mentions?.filter((x) => Number.isFinite(Number(x))).map((x) => Number(x));
      return {
        id: m.id,
        content: deletedForEveryone ? '' : payload.text || '',
        sender: 'agent',
        senderName,
        senderAgentId: m.sender_agent_id ?? undefined,
        postedByAdmin: postedByAdmin || undefined,
        channelTeamId: m.team_id,
        timestamp: new Date(m.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
        sentAt: m.created_at,
        attachment: deletedForEveryone ? undefined : payload.attachment,
        replyTo: deletedForEveryone ? undefined : payload.replyTo,
        replyToMessageId: m.reply_to_message_id ?? undefined,
        editedAt: m.edited_at ?? undefined,
        deletedForEveryone: deletedForEveryone || undefined,
        reactions: mergeReactions(payload.reactions, cachedReactions),
        mentionAgentIds: mentionIds && mentionIds.length > 0 ? mentionIds : undefined,
        teamReceiptSummary: m.receipt_summary
          ? {
              recipient_count: m.receipt_summary.recipient_count,
              delivered_count: m.receipt_summary.delivered_count,
              read_count: m.receipt_summary.read_count,
            }
          : undefined,
      };
    },
    [broadcastMode, viewerAgentId, teamId],
  );

  const fetchTeamMessagesSince = useCallback(
    async (sinceIso: string) => {
      if (!teamId) return;
      const url = new URL(`${API_BASE}/api/teams/${Number(teamId)}/channel/messages`);
      url.searchParams.set('tenant_id', String(TENANT_ID));
      url.searchParams.set('since', sinceIso);
      try {
        const res = await fetch(url.toString(), { headers: teamChannelJsonHeaders() });
        if (!res.ok) return;
        const raw = await res.json();
        const rows = (Array.isArray(raw) ? raw : (raw.messages ?? [])) as TeamChannelMessageRow[];
        const mapped = rows.map((m) => mapTeamRowToMessage(m));
        if (mapped.length === 0) return;
        setMessages((prev) => {
          const byId = new Map<number, Message>();
          for (const m of prev) byId.set(m.id, m);
          for (const m of mapped) byId.set(m.id, m);
          return Array.from(byId.values()).sort((a, b) => a.id - b.id);
        });
      } catch {
        // ignore
      }
    },
    [teamId, mapTeamRowToMessage, API_BASE, TENANT_ID],
  );

  const fetchTeamMessagesSinceRef = useRef(fetchTeamMessagesSince);
  fetchTeamMessagesSinceRef.current = fetchTeamMessagesSince;

  const loadTeamOlderMessages = useCallback(async () => {
    if (!isInternalChat || !isTeamChannel || !teamId || teamLoadingOlder || !teamHasMoreOlder) return;
    const el = scrollContainerRef.current;
    const prevH = el?.scrollHeight ?? 0;
    const prevT = el?.scrollTop ?? 0;
    const oldestId = messages[0]?.id;
    if (oldestId == null) return;
    setTeamLoadingOlder(true);
    try {
      const url = new URL(`${API_BASE}/api/teams/${Number(teamId)}/channel/messages`);
      url.searchParams.set('tenant_id', String(TENANT_ID));
      url.searchParams.set('limit', '50');
      url.searchParams.set('before_id', String(oldestId));
      const res = await fetch(url.toString(), { headers: teamChannelJsonHeaders() });
      if (!res.ok) return;
      const raw = await res.json();
      const page = Array.isArray(raw) ? { messages: raw, has_more_older: false } : raw;
      const rows = (page.messages ?? []) as TeamChannelMessageRow[];
      setTeamHasMoreOlder(Boolean(page.has_more_older));
      const olderMapped = rows.map((m) => mapTeamRowToMessage(m));
      setMessages((prev) => {
        const byId = new Map<number, Message>();
        for (const m of olderMapped) byId.set(m.id, m);
        for (const m of prev) byId.set(m.id, m);
        return Array.from(byId.values()).sort((a, b) => a.id - b.id);
      });
      requestAnimationFrame(() => {
        const s = scrollContainerRef.current;
        if (s) s.scrollTop = s.scrollHeight - prevH + prevT;
      });
    } catch {
      // ignore
    } finally {
      setTeamLoadingOlder(false);
    }
  }, [
    isInternalChat,
    isTeamChannel,
    teamId,
    teamLoadingOlder,
    teamHasMoreOlder,
    messages,
    mapTeamRowToMessage,
    API_BASE,
    TENANT_ID,
  ]);

  const teamSendDeliveryAckRef = useRef<(ids: number[]) => void>(() => {});

  const handleTeamChannelWs = useCallback(
    (ev: TeamChannelWsEvent) => {
      if (ev.type === 'NEW_MESSAGE' || ev.type === 'MESSAGE_UPDATED') {
        const row = ev.message as TeamChannelMessageRow;
        const mapped = mapTeamRowToMessage(row);
        const isNew = ev.type === 'NEW_MESSAGE';
        setMessages((prev) => {
          const idx = prev.findIndex((x) => x.id === mapped.id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = mapped;
            return next;
          }
          const merged = [...prev, mapped].sort((a, b) => a.id - b.id);
          return merged;
        });
        if (isNew && !teamNearBottomRef.current) {
          const isMine = broadcastMode
            ? !!mapped.postedByAdmin && showBroadcastInput
            : mapped.senderAgentId === viewerAgentId && viewerAgentId > 0;
          if (!isMine) setTeamNewBelowOpen(true);
        }
        if (isNew && viewerAgentId > 0) {
          const isMine = broadcastMode
            ? !!mapped.postedByAdmin && showBroadcastInput
            : mapped.senderAgentId === viewerAgentId;
          if (!isMine) {
            teamSendDeliveryAckRef.current([mapped.id]);
          }
        }
        return;
      }
      if (ev.type === 'RECEIPTS_UPDATED' && Array.isArray(ev.summaries)) {
        setMessages((prev) =>
          prev.map((m) => {
            const s = ev.summaries.find((x) => x.message_id === m.id);
            if (!s) return m;
            return {
              ...m,
              teamReceiptSummary: {
                recipient_count: s.recipient_count,
                delivered_count: s.delivered_count,
                read_count: s.read_count,
              },
            };
          }),
        );
        return;
      }
      if (ev.type === 'READ_STATE') {
        setMemberReadStates((prev) => ({
          ...prev,
          [String(ev.agent_id)]: ev.last_read_message_id,
        }));
        return;
      }
      if (ev.type === 'TYPING') {
        const self = viewerAgentId && ev.agent_id === viewerAgentId;
        if (self) return;
        const key = `${ev.agent_id ?? 'x'}:${ev.name}`;
        if (ev.active) {
          setTeamTypers((prev) => ({
            ...prev,
            [key]: { name: ev.name, until: Date.now() + 4000 },
          }));
        } else {
          setTeamTypers((prev) => {
            const { [key]: _, ...rest } = prev;
            return rest;
          });
        }
      }
    },
    [mapTeamRowToMessage, viewerAgentId, broadcastMode, showBroadcastInput],
  );

  const { sendTyping: sendTypingWs, sendDeliveryAck: teamSendDeliveryAck } = useTeamChannelRealtime(
    Boolean(isInternalChat && isTeamChannel && teamId && typeof window !== 'undefined'),
    teamId ? Number(teamId) : null,
    TENANT_ID,
    handleTeamChannelWs,
    {
      onOpen: () => {
        const since = teamLastSyncIsoRef.current;
        if (since) void fetchTeamMessagesSinceRef.current(since);
      },
    },
  );
  teamSendDeliveryAckRef.current = teamSendDeliveryAck;

  const teamReadFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const teamPendingReadMaxRef = useRef(0);

  useEffect(() => {
    if (!isInternalChat || !isTeamChannel || !teamId) return;
    setMessages([]);
    setMemberReadStates({});
    setTeamTypers({});
    setTeamHasMoreOlder(false);
    setTeamNewBelowOpen(false);
    initialScrollThreadKeyDoneRef.current = '';
    let cancelled = false;
    const load = async () => {
      try {
        const msgUrl = new URL(`${API_BASE}/api/teams/${Number(teamId)}/channel/messages`);
        msgUrl.searchParams.set('tenant_id', String(TENANT_ID));
        msgUrl.searchParams.set('limit', '50');
        const readUrl = `${API_BASE}/api/teams/${Number(teamId)}/channel/member-read-states?tenant_id=${TENANT_ID}`;
        const [msgRes, readRes] = await Promise.all([
          fetch(msgUrl.toString(), { headers: teamChannelJsonHeaders() }),
          fetch(readUrl, { headers: teamChannelJsonHeaders() }),
        ]);
        if (!msgRes.ok) throw new Error('Failed to load team messages');
        const raw = await msgRes.json();
        const page = Array.isArray(raw) ? { messages: raw, has_more_older: false } : raw;
        const rows = (page.messages ?? []) as TeamChannelMessageRow[];
        if (cancelled) return;
        const mapped: Message[] = rows.map((m) => mapTeamRowToMessage(m));
        setMessages(mapped);
        setTeamHasMoreOlder(Boolean(page.has_more_older));
        if (readRes.ok) {
          const arr = (await readRes.json()) as { agent_id: number; last_read_message_id: number }[];
          const readMap: Record<string, number> = {};
          for (const r of arr) {
            readMap[String(r.agent_id)] = r.last_read_message_id;
          }
          if (!cancelled) setMemberReadStates(readMap);
        }
      } catch {
        if (!cancelled) setMessages([]);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [isInternalChat, isTeamChannel, teamId, API_BASE, TENANT_ID, mapTeamRowToMessage]);

  useEffect(() => {
    if (!isInternalChat || !isTeamChannel || !teamId || readOnly || !viewerAgentId) return;
    const ids = messages.map((m) => m.id);
    if (ids.length === 0) return;
    const maxId = Math.max(...ids);
    teamPendingReadMaxRef.current = Math.max(teamPendingReadMaxRef.current, maxId);
    if (teamReadFlushTimerRef.current) clearTimeout(teamReadFlushTimerRef.current);
    teamReadFlushTimerRef.current = setTimeout(() => {
      teamReadFlushTimerRef.current = null;
      if (!teamNearBottomRef.current) return;
      const v = teamPendingReadMaxRef.current;
      void fetch(`${API_BASE}/api/teams/${Number(teamId)}/channel/read-state`, {
        method: 'POST',
        headers: teamChannelJsonHeaders(),
        body: JSON.stringify({ tenant_id: TENANT_ID, last_read_message_id: v }),
      }).catch(() => undefined);
    }, 700);
    return () => {
      if (teamReadFlushTimerRef.current) clearTimeout(teamReadFlushTimerRef.current);
    };
  }, [isInternalChat, isTeamChannel, teamId, readOnly, viewerAgentId, messages, API_BASE, TENANT_ID]);

  useEffect(() => {
    if (!isTeamChannel) return;
    const t = window.setInterval(() => {
      const now = Date.now();
      setTeamTypers((prev) => {
        const next = { ...prev };
        let changed = false;
        for (const k of Object.keys(next)) {
          if (next[k].until < now) {
            delete next[k];
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 800);
    return () => window.clearInterval(t);
  }, [isTeamChannel]);

  const dmConversation = isDmPage && dmSlug ? getConversationBySlug(dmSlug) : undefined;
  const dmConversationIdRaw = dmConversation ? Number(dmConversation.id) : NaN;
  const dmConversationId =
    dmConversation != null && Number.isFinite(dmConversationIdRaw) && dmConversationIdRaw > 0
      ? dmConversationIdRaw
      : null;

  const dmSendDeliveryAckRef = useRef<(ids: number[]) => void>(() => {});

  const handleDmWs = useCallback(
    (ev: DmWsEvent) => {
      if (!dmSlug) return;
      if (ev.type === 'DM_RECEIPTS_UPDATED') {
        for (const r of ev.receipts) {
          patchDmMessage(dmSlug, r.message_id, {
            peerDeliveredAt: r.delivered_at ?? undefined,
            peerReadAt: r.read_at ?? undefined,
          });
        }
        return;
      }
      if (ev.type === 'NEW_DM_MESSAGE') {
        const row = ev.message;
        mergeIncomingDmMessage(dmSlug, row);
        if (String(row.sender_agent_id) !== String(viewerAgentId) && !dmNearBottomRef.current) {
          reportDmUnread(dmSlug);
          setDmNewBelowOpen(true);
        }
        if (String(row.sender_agent_id) !== String(viewerAgentId) && viewerAgentId > 0) {
          dmSendDeliveryAckRef.current([row.id]);
        }
        return;
      }
      if (ev.type === 'DM_MESSAGE_UPDATED') {
        mergeIncomingDmMessage(dmSlug, ev.message);
      }
    },
    [dmSlug, mergeIncomingDmMessage, viewerAgentId, reportDmUnread, patchDmMessage],
  );

  const { sendDeliveryAck: dmSendDeliveryAck } = useDmConversationRealtime(
    Boolean(
      isInternalChat && isDmPage && dmSlug && dmConversationId != null && dmConversationId > 0 && viewerAgentId > 0,
    ),
    dmConversationId,
    TENANT_ID,
    viewerAgentId > 0 ? viewerAgentId : null,
    handleDmWs,
    {
      // New messages arrive via WebSocket; avoid an extra history fetch on every reconnect (reduces flicker).
      onOpen: () => {},
    },
  );
  dmSendDeliveryAckRef.current = dmSendDeliveryAck;

  useEffect(() => {
    if (!isDmPage) return;
    initialScrollThreadKeyDoneRef.current = '';
    setDmNewBelowOpen(false);
  }, [isDmPage, dmSlug]);

  useEffect(() => {
    if (!isTeamChannel || messages.length === 0) return;
    let max = '';
    for (const m of messages) {
      const t = m.sentAt || '';
      if (t > max) max = t;
    }
    if (max) teamLastSyncIsoRef.current = max;
  }, [isTeamChannel, messages]);

  useEffect(() => {
    if (!isDmPage || !dmSlug) return;
    const rows = getMessagesBySlug(dmSlug);
    let max = '';
    for (const m of rows) {
      if (m.createdAt > max) max = m.createdAt;
    }
    if (max) dmLastSyncIsoRef.current = max;
  }, [isDmPage, dmSlug, getMessagesBySlug]);

  const toTeamPayload = (message: Message): TeamChannelPayload => ({
    text: message.content || '',
    attachment: message.attachment,
    replyTo: message.replyTo,
    reactions: message.reactions,
    mentions: message.mentionAgentIds?.length ? message.mentionAgentIds : undefined,
  });

  const persistTeamMessagePayload = async (message: Message) => {
    if (!isInternalChat || !isTeamChannel) return;
    const teamIdForApi = message.channelTeamId ?? (teamId ? Number(teamId) : 0);
    if (!teamIdForApi) return;
    try {
      await fetch(`${API_BASE}/api/teams/${teamIdForApi}/channel/messages/${message.id}`, {
        method: 'PATCH',
        headers: teamChannelJsonHeaders(),
        body: JSON.stringify({
          tenant_id: TENANT_ID,
          content: encodeTeamMessageContent(toTeamPayload(message)),
        }),
      });
    } catch {
      // Keep optimistic UI even if persistence fails.
    }
  };

  const getMessageStyle = (message: Message, outgoing: boolean) => {
    const mentioned =
      isTeamChannel &&
      viewerAgentId > 0 &&
      message.mentionAgentIds?.includes(viewerAgentId);
    if (outgoing) {
      return 'bg-[#d9fdd3] text-[#111b21] shadow-[0_1px_0.5px_rgba(11,20,26,0.13)]';
    }
    if (mentioned) {
      return 'bg-[#fff9c4] text-[#111b21] shadow-[0_1px_0.5px_rgba(11,20,26,0.13)] border border-[#53bdeb]/40';
    }
    return 'bg-white text-[#111b21] shadow-[0_1px_0.5px_rgba(11,20,26,0.13)] border border-black/[0.06]';
  };

  const isOutgoingMessage = (message: Message) => {
    if (isInternalChat && isTeamChannel) {
      if (broadcastMode) {
        return message.postedByAdmin === true || message.senderName === 'Admin';
      }
      if (viewerAgentId && message.senderAgentId) return message.senderAgentId === viewerAgentId;
      return message.senderName === 'You';
    }
    if (isInternalChat) return message.senderName === 'You';
    if (isInboxPage && !isInternalChat) {
      return message.sender === 'agent' || message.sender === 'ai';
    }
    return message.sender === 'customer' || message.senderName === 'You';
  };

  const addSystemNote = (content: string) => {
    const now = new Date();
    setMessages((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        content,
        sender: 'ai' as const,
        senderName: 'System',
        timestamp: now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
        sentAt: now.toISOString(),
      },
    ]);
  };

  const closeMenus = () => {
    setShowMoreMenu(false);
    setShowTransferMenu(false);
  };

  const toggleStar = (id: number) => {
    setStarredIds((prev) =>
      prev.includes(id) ? prev.filter((mId) => mId !== id) : [...prev, id],
    );
  };

  const scrollToMessage = (id: number) => {
    const el = document.getElementById(`message-${id}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setShowGroupInfo(false);
    }
  };

  const addReaction = (id: number, emoji: string) => {
    const target = messages.find((m) => m.id === id);
    if (!target) return;
    const list = target.reactions ?? [];
    const withoutMe = list.filter((r) => r.userId !== reactionActorId);
    const existing = list.find((r) => r.userId === reactionActorId);
    const updated: Message =
      existing?.emoji === emoji
        ? { ...target, reactions: withoutMe.length > 0 ? withoutMe : undefined }
        : {
            ...target,
            reactions: [
              ...withoutMe,
              { emoji, userId: reactionActorId, userName: reactionActorName, reactedAt: new Date().toISOString() },
            ],
          };
    setMessages((prev) => prev.map((m) => (m.id === id ? updated : m)));
    writeReactionCache(id, updated.reactions);
    void persistTeamMessagePayload(updated);
    setActiveReactionPickerId(null);
    setActiveMessageMenuId(null);
  };

  const formatReactionTime = (iso: string) => {
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  };

  const formatMessageTime = (sentAt?: string, fallbackTimestamp?: string) => {
    if (sentAt) return new Date(sentAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    return fallbackTimestamp ?? '';
  };

  const formatDateLabel = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });
  };

  const getMessageDateKey = (m: Message) => {
    if (m.sentAt) return m.sentAt.slice(0, 10);
    return new Date().toISOString().slice(0, 10);
  };

  const isEmojiOnly = (text: string) => {
    const t = text.trim();
    if (!t) return false;
    return /^[\p{Emoji_Presentation}\p{Emoji}\s\uFE0F]+$/u.test(t) && t.length <= 20;
  };

  const getReceiptPeersForMessage = (message: Message): { id: number; name: string }[] => {
    if (!teamMemberRoster.length) return [];
    const peers = teamMemberRoster
      .map((r) => ({ id: Number.parseInt(r.agentId, 10), name: r.name }))
      .filter((p) => Number.isFinite(p.id) && p.id >= 1);
    if (message.postedByAdmin || message.senderName === 'Admin') return peers;
    const sid = message.senderAgentId;
    if (!sid) return peers;
    return peers.filter((p) => p.id !== sid);
  };

  const renderTeamMessageBody = (content: string) => {
    if (!isTeamChannel || !content) return content;
    const parts: ReactNode[] = [];
    const re = /@([^\s@]+)/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let mi = 0;
    while ((m = re.exec(content)) !== null) {
      if (m.index > last) parts.push(<span key={`t-${mi++}`}>{content.slice(last, m.index)}</span>);
      const token = m[1];
      const hit = mentionRoster.find((r) => r.name.toLowerCase() === token.toLowerCase());
      parts.push(
        <span key={`m-${m.index}`} className={hit ? 'font-semibold text-[#53bdeb]' : 'text-[#8696a0]'}>
          @{token}
        </span>,
      );
      last = m.index + m[0].length;
    }
    if (last < content.length) parts.push(<span key={`t-end-${mi}`}>{content.slice(last)}</span>);
    return parts.length > 0 ? parts : content;
  };

  const formatVoiceDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const toggleVoicePlayback = (messageId: number, url: string, durationSeconds: number) => {
    const id = messageId;
    if (playingVoiceId === id) {
      voiceAudioRef.current?.pause();
      setPlayingVoiceId(null);
      return;
    }
    if (voiceAudioRef.current) {
      voiceAudioRef.current.pause();
      voiceAudioRef.current = null;
    }
    const audio = new Audio(url);
    voiceAudioRef.current = audio;
    voiceMessageIdRef.current = id;
    setPlayingVoiceId(id);
    const updateProgress = () => {
      if (voiceMessageIdRef.current === id && audio.duration && isFinite(audio.duration)) {
        setVoiceProgress((prev) => ({ ...prev, [id]: audio.currentTime / audio.duration }));
      }
    };
    audio.addEventListener('timeupdate', updateProgress);
    audio.addEventListener('ended', () => {
      setVoiceProgress((prev) => ({ ...prev, [id]: 1 }));
      setPlayingVoiceId(null);
      voiceAudioRef.current = null;
      voiceMessageIdRef.current = null;
    });
    audio.play().catch(() => {
      setPlayingVoiceId(null);
      voiceAudioRef.current = null;
    });
  };

  const VOICE_WAVEFORM_BARS = [40, 70, 45, 85, 55, 65, 50, 90, 60, 75, 48, 82, 52, 68];

  const filteredMessages = messages.filter((m) => !deletedForMeIds.includes(m.id));
  const threadSearchTrim = threadSearchQuery.trim().toLowerCase();
  const threadSearchMatches =
    threadSearchTrim.length > 0
      ? filteredMessages.filter((m) => m.content.toLowerCase().includes(threadSearchTrim))
      : [];
  const messageGroups = (() => {
    const list: { dateKey: string; label: string; messages: Message[] }[] = [];
    let currentKey: string | null = null;
    for (const m of filteredMessages) {
      const key = getMessageDateKey(m);
      const label = formatDateLabel(m.sentAt ?? new Date().toISOString());
      if (key !== currentKey) {
        list.push({ dateKey: key, label, messages: [] });
        currentKey = key;
      }
      list[list.length - 1].messages.push(m);
    }
    return list;
  })();

  const allDateKeys = [
    ...new Set([
      ...messageGroups.map((g) => g.dateKey),
      ...teamEvents.map((e) => e.sentAt.slice(0, 10)),
    ]),
  ].sort();

  const unifiedGroups = allDateKeys.map((dateKey) => {
    const msgGroup = messageGroups.find((g) => g.dateKey === dateKey);
    const label = msgGroup?.label ?? formatDateLabel(dateKey + 'T12:00:00');
    const eventsForDate = teamEvents.filter((e) => e.sentAt.slice(0, 10) === dateKey);
    return {
      dateKey,
      label,
      messages: msgGroup?.messages ?? [],
      events: eventsForDate,
    };
  });

  const inboxThreadSkeleton =
    isInboxPage &&
    !isInternalChat &&
    inboxConv != null &&
    inboxConv.selectedId != null &&
    inboxConv.loadingConversationId === inboxConv.selectedId;
  const dmMessagesEmpty =
    isInternalChat && isDmPage && dmSlug != null && getMessagesBySlug(dmSlug).length === 0;
  const dmThreadSkeleton =
    isInternalChat &&
    isDmPage &&
    dmSlug != null &&
    dmMessagesEmpty &&
    loadingDmSlug === dmSlug;
  const showChatThreadSkeleton =
    (inboxThreadSkeleton && filteredMessages.length === 0) || dmThreadSkeleton;

  const sharedChatMedia = messages
    .filter((m) => m.attachment?.type === 'photo' && m.attachment.url)
    .map((m) => ({
      id: `chat-media-${m.id}`,
      name: m.attachment!.name || 'Image',
      url: m.attachment!.url,
      isHeic: isHeicLikeAttachment(m.attachment),
    }));

  const sharedChatDocs = messages
    .filter((m) => m.attachment?.type === 'file' && m.attachment.url)
    .map((m) => ({
      id: `chat-doc-${m.id}`,
      name: m.attachment!.name || 'Document',
      url: m.attachment!.url,
    }));

  const handleScrollStickyDate = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top + 72;
    const dateEls = el.querySelectorAll('[data-date-key]');
    let current: string | null = null;
    dateEls.forEach((node) => {
      const rect = (node as HTMLElement).getBoundingClientRect();
      if (rect.top <= top) current = (node as HTMLElement).getAttribute('data-date-key');
    });
    setStickyDate(current);
  };

  const handleChatScroll = useCallback(() => {
    handleScrollStickyDate();
    const el = scrollContainerRef.current;
    if (!el) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    const distBottom = scrollHeight - scrollTop - clientHeight;
    const near = distBottom <= BOTTOM_THRESHOLD_PX;
    teamNearBottomRef.current = near;
    dmNearBottomRef.current = near;
    inboxNearBottomRef.current = near;
    if (near) {
      setTeamNewBelowOpen(false);
      setDmNewBelowOpen(false);
      setInboxNewBelowOpen(false);
      if (isDmPage && dmSlug) clearDmUnread(dmSlug);
    }
    if (
      isInboxPage &&
      !isInternalChat &&
      inboxConv?.selectedId != null &&
      inboxConv.inboxHasMoreOlder &&
      inboxConv.loadOlderInboxMessages &&
      inboxConv.inboxHasMoreOlder(inboxConv.selectedId) &&
      !inboxLoadingOlder &&
      scrollTop < 100
    ) {
      const prevH = el.scrollHeight;
      const prevT = el.scrollTop;
      setInboxLoadingOlder(true);
      void inboxConv.loadOlderInboxMessages(inboxConv.selectedId).finally(() => {
        setInboxLoadingOlder(false);
        requestAnimationFrame(() => {
          const s = scrollContainerRef.current;
          if (s) s.scrollTop = s.scrollHeight - prevH + prevT;
        });
      });
    }
    if (isTeamChannel && teamHasMoreOlder && !teamLoadingOlder && scrollTop < 100) {
      void loadTeamOlderMessages();
    }
    if (isDmPage && dmSlug && dmHasMoreOlder(dmSlug) && !loadingOlderDmSlug && scrollTop < 100) {
      void loadOlderDmMessages(dmSlug);
    }
    if (
      near &&
      isInboxPage &&
      !isInternalChat &&
      inboxConv?.selectedId != null &&
      inboxConv.syncInboxReadState
    ) {
      const sid = inboxConv.selectedId;
      const msgs = inboxConv.getMessages(sid);
      const maxId = msgs.length ? Math.max(...msgs.map((m) => m.id)) : 0;
      if (maxId > 0) {
        const prev = lastSyncedInboxReadRef.current;
        if (!prev || prev.convId !== sid || prev.id !== maxId) {
          lastSyncedInboxReadRef.current = { convId: sid, id: maxId };
          void inboxConv.syncInboxReadState(sid, maxId);
        }
      }
    }
  }, [
    isTeamChannel,
    isInboxPage,
    isInternalChat,
    isDmPage,
    dmSlug,
    inboxConv,
    inboxLoadingOlder,
    teamHasMoreOlder,
    teamLoadingOlder,
    loadTeamOlderMessages,
    dmHasMoreOlder,
    loadingOlderDmSlug,
    loadOlderDmMessages,
    clearDmUnread,
  ]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    handleChatScroll();
    el.addEventListener('scroll', handleChatScroll);
    return () => el.removeEventListener('scroll', handleChatScroll);
  }, [handleChatScroll, filteredMessages.length, teamEvents.length]);

  const initialScrollKey =
    isTeamChannel && teamId
      ? `team:${teamId}`
      : isDmPage && dmSlug
        ? `dm:${dmSlug}`
        : isInboxPage && !isInternalChat && inboxConv?.selectedId != null
          ? `inbox:${inboxConv.selectedId}`
          : '';

  useLayoutEffect(() => {
    if (!initialScrollKey || showChatThreadSkeleton || filteredMessages.length === 0) return;
    if (initialScrollThreadKeyDoneRef.current === initialScrollKey) return;
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    initialScrollThreadKeyDoneRef.current = initialScrollKey;
    teamNearBottomRef.current = true;
    dmNearBottomRef.current = true;
    inboxNearBottomRef.current = true;
    if (initialScrollKey.startsWith('dm:') && dmSlug) clearDmUnread(dmSlug);
  }, [initialScrollKey, showChatThreadSkeleton, filteredMessages.length, dmSlug, clearDmUnread]);

  useEffect(() => {
    if (!initialScrollKey) return;
    if (
      !teamNearBottomRef.current &&
      !dmNearBottomRef.current &&
      !inboxNearBottomRef.current
    )
      return;
    const el = scrollContainerRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      if (
        !teamNearBottomRef.current &&
        !dmNearBottomRef.current &&
        !inboxNearBottomRef.current
      )
        return;
      el.scrollTop = el.scrollHeight;
    });
  }, [filteredMessages.length, initialScrollKey]);

  const flashCopyToast = useCallback(() => {
    if (copyToastTimerRef.current) clearTimeout(copyToastTimerRef.current);
    setCopyToastVisible(true);
    copyToastTimerRef.current = setTimeout(() => {
      setCopyToastVisible(false);
      copyToastTimerRef.current = null;
    }, 2000);
  }, []);

  const deleteMessage = async (id: number) => {
    if (isInboxPage && !isInternalChat) {
      try {
        const res = await fetch(`${API_BASE}/api/messaging/messages/${id}/for-everyone`, {
          method: 'DELETE',
          headers: teamChannelJsonHeaders(),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          addSystemNote(
            typeof err.detail === 'string' ? err.detail : 'Could not delete for everyone.',
          );
          setActiveMessageMenuId(null);
          return;
        }
        if (inboxConv?.selectedId != null) {
          inboxConv.patchInboxMessage(inboxConv.selectedId, id, {
            content: '[Message deleted]',
            deletedForEveryone: true,
          });
        }
      } catch {
        addSystemNote('Could not delete for everyone.');
        setActiveMessageMenuId(null);
        return;
      }
    } else if (isInternalChat && isTeamChannel && teamId) {
      try {
        const res = await fetch(
          `${API_BASE}/api/teams/${Number(teamId)}/channel/messages/${id}/for-everyone?tenant_id=${TENANT_ID}`,
          { method: 'DELETE', headers: teamChannelJsonHeaders() },
        );
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          addSystemNote(
            typeof err.detail === 'string' ? err.detail : 'Could not delete for everyone.',
          );
          setActiveMessageMenuId(null);
          return;
        }
        setMessages((prev) =>
          prev.map((m) => (m.id === id ? { ...m, deletedForEveryone: true, content: '' } : m)),
        );
      } catch {
        addSystemNote('Could not delete for everyone.');
        setActiveMessageMenuId(null);
        return;
      }
    } else if (isInternalChat && isDmPage && dmSlug) {
      const conv = getConversationBySlug(dmSlug);
      if (!conv) {
        setActiveMessageMenuId(null);
        return;
      }
      try {
        const res = await fetch(
          `${API_BASE}/api/internal-dm/messages/${id}/for-everyone?tenant_id=${TENANT_ID}&conversation_id=${encodeURIComponent(conv.id)}`,
          { method: 'DELETE', headers: teamChannelJsonHeaders() },
        );
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          addSystemNote(
            typeof err.detail === 'string' ? err.detail : 'Could not delete for everyone.',
          );
          setActiveMessageMenuId(null);
          return;
        }
        setMessages((prev) =>
          prev.map((m) => (m.id === id ? { ...m, deletedForEveryone: true, content: '' } : m)),
        );
      } catch {
        addSystemNote('Could not delete for everyone.');
        setActiveMessageMenuId(null);
        return;
      }
    } else {
      setMessages((prev) => prev.filter((m) => m.id !== id));
    }
    setStarredIds((prev) => prev.filter((mId) => mId !== id));
    setDeletedForMeIds((prev) => prev.filter((mId) => mId !== id));
    setActiveMessageMenuId(null);
  };

  const deleteForMe = async (id: number) => {
    if (isInboxPage && !isInternalChat) {
      try {
        const res = await fetch(`${API_BASE}/api/messaging/messages/${id}/for-me`, {
          method: 'DELETE',
          headers: teamChannelJsonHeaders(),
        });
        if (!res.ok) {
          addSystemNote('Could not remove message.');
          setActiveMessageMenuId(null);
          return;
        }
      } catch {
        addSystemNote('Could not remove message.');
        setActiveMessageMenuId(null);
        return;
      }
    } else if (isInternalChat && isTeamChannel && teamId) {
      try {
        const res = await fetch(
          `${API_BASE}/api/teams/${Number(teamId)}/channel/messages/${id}/for-me?tenant_id=${TENANT_ID}`,
          { method: 'DELETE', headers: teamChannelJsonHeaders() },
        );
        if (!res.ok) {
          addSystemNote('Could not remove message.');
          setActiveMessageMenuId(null);
          return;
        }
      } catch {
        addSystemNote('Could not remove message.');
        setActiveMessageMenuId(null);
        return;
      }
    } else if (isInternalChat && isDmPage && dmSlug) {
      const conv = getConversationBySlug(dmSlug);
      if (conv) {
        try {
          const res = await fetch(
            `${API_BASE}/api/internal-dm/messages/${id}/for-me?tenant_id=${TENANT_ID}&conversation_id=${encodeURIComponent(conv.id)}`,
            { method: 'DELETE', headers: teamChannelJsonHeaders() },
          );
          if (!res.ok) {
            addSystemNote('Could not remove message.');
            setActiveMessageMenuId(null);
            return;
          }
        } catch {
          addSystemNote('Could not remove message.');
          setActiveMessageMenuId(null);
          return;
        }
      }
    }
    setDeletedForMeIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setStarredIds((prev) => prev.filter((mId) => mId !== id));
    setActiveMessageMenuId(null);
  };

  const retryFailedInboxSend = (m: Message) => {
    if (!inboxConv?.selectedId || !isInboxPage || isInternalChat) return;
    const convId = inboxConv.selectedId;
    inboxConv.removeInboxMessage(convId, m.id);
    const now = new Date();
    const nextId = Date.now();
    const im: InboxMessage = {
      id: nextId,
      content: m.content,
      sender: 'agent',
      senderName: 'You',
      timestamp: now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
      sentAt: now.toISOString(),
      replyTo: m.replyTo,
      replyToMessageId: m.replyToMessageId,
      messageStatus: { sent: true, delivered: false, read: false },
    };
    inboxConv.appendMessage(convId, im);
  };

  const submitThreadMessageEdit = async () => {
    if (!threadMessageEdit) return;
    const trimmed = threadMessageEdit.text.trim();
    if (!trimmed) {
      addSystemNote('Message cannot be empty.');
      return;
    }

    if (threadMessageEdit.source === 'inbox') {
      const convId = inboxConv?.selectedId;
      if (convId == null || !inboxConv) return;
      const { id } = threadMessageEdit;
      try {
        const res = await fetch(`${API_BASE}/api/messaging/messages/${id}`, {
          method: 'PATCH',
          headers: teamChannelJsonHeaders(),
          body: JSON.stringify({ content: trimmed }),
        });
        if (!res.ok) {
          addSystemNote('Could not save edit.');
          return;
        }
        const saved = (await res.json()) as { edited_at?: string | null; content?: string };
        inboxConv.patchInboxMessage(convId, id, {
          content: saved.content ?? trimmed,
          editedAt: saved.edited_at ?? new Date().toISOString(),
        });
        setThreadMessageEdit(null);
      } catch {
        addSystemNote('Could not save edit.');
      }
      return;
    }

    if (threadMessageEdit.source === 'dm') {
      if (!dmSlug) return;
      const conv = getConversationBySlug(dmSlug);
      if (!conv) return;
      const { id } = threadMessageEdit;
      try {
        const res = await fetch(`${API_BASE}/api/internal-dm/messages/${id}`, {
          method: 'PATCH',
          headers: teamChannelJsonHeaders(),
          body: JSON.stringify({
            tenant_id: TENANT_ID,
            conversation_id: Number(conv.id),
            content: trimmed,
          }),
        });
        if (!res.ok) {
          addSystemNote('Could not save edit.');
          return;
        }
        const saved = (await res.json()) as {
          content: string;
          edited_at?: string | null;
        };
        patchDmMessage(dmSlug, id, {
          content: saved.content ?? trimmed,
          editedAt: saved.edited_at ?? new Date().toISOString(),
        });
        setThreadMessageEdit(null);
      } catch {
        addSystemNote('Could not save edit.');
      }
      return;
    }

    if (threadMessageEdit.source === 'team') {
      if (!teamId) return;
      const target = messages.find((m) => m.id === threadMessageEdit.id);
      if (!target) return;
      const { id } = threadMessageEdit;
      try {
        const payloadJson = encodeTeamMessageContent({
          ...toTeamPayload(target),
          text: trimmed,
        });
        const res = await fetch(`${API_BASE}/api/teams/${Number(teamId)}/channel/messages/${id}`, {
          method: 'PATCH',
          headers: teamChannelJsonHeaders(),
          body: JSON.stringify({
            tenant_id: TENANT_ID,
            content: typeof payloadJson === 'string' ? payloadJson : String(payloadJson ?? ''),
          }),
        });
        if (!res.ok) {
          addSystemNote('Could not save edit.');
          return;
        }
        const saved = (await res.json()) as TeamChannelMessageRow;
        const mapped = mapTeamRowToMessage(saved);
        setMessages((prev) => prev.map((m) => (m.id === mapped.id ? mapped : m)));
        setThreadMessageEdit(null);
      } catch {
        addSystemNote('Could not save edit.');
      }
    }
  };

  const sendMessage = async () => {
    const text = inputValue.trim();
    const hasContent = text.length > 0 || pendingAttachment;
    if (!hasContent) return;
    const nextId = Math.max(0, ...messages.map((m) => m.id)) + 1;
    const now = new Date();
    const newMsg: Message = {
      id: nextId,
      content: text || (pendingAttachment?.type === 'voice' ? 'Voice message' : pendingAttachment?.name || 'Attachment'),
      sender: 'agent' as const,
      senderName: showBroadcastInput ? 'Admin' : 'You',
      timestamp: now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
      sentAt: now.toISOString(),
      replyTo: replyingTo ?? undefined,
      attachment: pendingAttachment ?? undefined,
    };
    if (isInternalChat && isDmPage && dmSlug) {
      let outContent = text;
      try {
        if (pendingAttachment?.type === 'voice') {
          const dataUrl = await blobUrlToDataUrl(pendingAttachment.url);
          if (dataUrl.length > 2_000_000) {
            addSystemNote('Voice message is too large. Try a shorter recording.');
            return;
          }
          outContent = encodeDmMessagePayload({
            text: text,
            attachment: { ...pendingAttachment, url: dataUrl },
          });
        } else if (pendingAttachment) {
          addSystemNote('Direct messages support text or voice only.');
          return;
        } else if (!text) {
          return;
        }
        await sendMessageBySlug(dmSlug, outContent, replyingTo?.id);
      } catch {
        addSystemNote('Message failed to send. Please try again.');
        return;
      }
      if (pendingAttachment?.url?.startsWith('blob:')) {
        try {
          URL.revokeObjectURL(pendingAttachment.url);
        } catch {
          // ignore
        }
      }
      setInputValue('');
      setReplyingTo(null);
      setPendingAttachment(null);
      setShowMentionDropdown(false);
      return;
    }
    if (isInternalChat && isTeamChannel && teamId) {
      try {
        sendTypingWs(false);
        const mentionList = Array.from(mentionIdsRef.current);
        let att = pendingAttachment ?? undefined;
        if (att?.type === 'voice' && att.url.startsWith('blob:')) {
          const dataUrl = await blobUrlToDataUrl(att.url);
          if (dataUrl.length > 2_000_000) {
            addSystemNote('Voice message is too large. Try a shorter recording.');
            return;
          }
          att = { ...att, url: dataUrl };
        }
        const payloadJson = encodeTeamMessageContent({
          text: text || '',
          attachment: att,
          replyTo: replyingTo ?? undefined,
          mentions: mentionList.length > 0 ? mentionList : undefined,
        });
        const body: Record<string, number | string | boolean> = {
          tenant_id: Number(TENANT_ID),
          content: typeof payloadJson === 'string' ? payloadJson : String(payloadJson ?? ''),
        };
        if (broadcastMode) {
          body.posted_by_admin = true;
        } else {
          const senderId = Number.parseInt(String(getCurrentAgent()?.id ?? ''), 10);
          if (!Number.isFinite(senderId) || senderId < 1) throw new Error('Agent not found');
          body.sender_agent_id = senderId;
        }
        if (typeof replyingTo?.id === 'number' && replyingTo.id > 0) {
          body.reply_to_message_id = replyingTo.id;
        }
        const res = await fetch(`${API_BASE}/api/teams/${Number(teamId)}/channel/messages`, {
          method: 'POST',
          headers: teamChannelJsonHeaders(),
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Failed to send team message');
        const saved = (await res.json()) as TeamChannelMessageRow;
        const mapped = mapTeamRowToMessage(saved);
        setMessages((prev) => {
          const idx = prev.findIndex((x) => x.id === mapped.id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = mapped;
            return next;
          }
          return [...prev, mapped].sort((a, b) => a.id - b.id);
        });
        mentionIdsRef.current = new Set();
      } catch {
        addSystemNote('Message failed to send. Please try again.');
      } finally {
        if (pendingAttachment?.type === 'voice' && pendingAttachment.url.startsWith('blob:')) {
          try {
            URL.revokeObjectURL(pendingAttachment.url);
          } catch {
            // ignore
          }
        }
        setInputValue('');
        setReplyingTo(null);
        setPendingAttachment(null);
        setShowMentionDropdown(false);
      }
      return;
    }
    if (isInboxPage && !isInternalChat && inboxConv?.selectedId != null) {
      const im: InboxMessage = {
        id: nextId,
        content: newMsg.content,
        sender: 'agent',
        senderName: 'You',
        timestamp: newMsg.timestamp,
        sentAt: newMsg.sentAt,
        replyTo: replyingTo ?? undefined,
        replyToMessageId: replyingTo?.id,
        messageStatus: { sent: true, delivered: false, read: false },
      };
      inboxConv.appendMessage(inboxConv.selectedId, im);
      inboxConv.markAgentReplied(inboxConv.selectedId);
      setInputValue('');
      setReplyingTo(null);
      setPendingAttachment(null);
      setShowMentionDropdown(false);
      return;
    }
    setMessages((prev) => [...prev, newMsg]);
    setInputValue('');
    setReplyingTo(null);
    setPendingAttachment(null);
    setShowMentionDropdown(false);
  };

  const DM_VOICE_MAX_SEC = 120;

  const clearRecordingTimer = () => {
    if (recordingTickRef.current) {
      clearInterval(recordingTickRef.current);
      recordingTickRef.current = null;
    }
  };

  const cancelVoiceRecording = () => {
    voiceCaptureCancelledRef.current = true;
    clearRecordingTimer();
    try {
      mediaRecorderRef.current?.stop();
    } catch {
      // ignore
    }
    mediaRecorderRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    setIsRecording(false);
    setRecordingPaused(false);
    setRecordingElapsedSec(0);
    recordingChunksRef.current = [];
  };

  function stopVoiceRecordingToReview() {
    const rec = mediaRecorderRef.current;
    if (rec && rec.state !== 'inactive') {
      try {
        rec.stop();
      } catch {
        // ignore
      }
    }
    mediaRecorderRef.current = null;
    clearRecordingTimer();
  }

  const startVoiceRecording = () => {
    if (typeof window === 'undefined' || !navigator.mediaDevices?.getUserMedia) return;
    voiceCaptureCancelledRef.current = false;
    setVoiceReviewAttachment(null);
    setShowAttachmentMenu(false);
    setShowEmojiPicker(false);
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      mediaStreamRef.current = stream;
      recordingChunksRef.current = [];
      recordingStartRef.current = Date.now();
      setRecordingElapsedSec(0);
      setRecordingPaused(false);
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordingChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        mediaStreamRef.current = null;
        clearRecordingTimer();
        setIsRecording(false);
        setRecordingPaused(false);
        if (voiceCaptureCancelledRef.current) {
          voiceCaptureCancelledRef.current = false;
          recordingChunksRef.current = [];
          return;
        }
        const blob = new Blob(recordingChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        recordingChunksRef.current = [];
        if (blob.size < 1) return;
        const url = URL.createObjectURL(blob);
        const durationSeconds = Math.max(
          1,
          Math.round((Date.now() - recordingStartRef.current) / 1000),
        );
        const att: MessageAttachment = {
          type: 'voice',
          name: 'Voice message',
          url,
          durationSeconds,
        };
        if (isInternalChat) {
          setVoiceReviewAttachment(att);
        } else {
          setPendingAttachment(att);
        }
      };
      try {
        recorder.start(250);
      } catch {
        recorder.start();
      }
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      clearRecordingTimer();
      recordingTickRef.current = setInterval(() => {
        setRecordingElapsedSec((s) => {
          const next = s + 1;
          if (next >= DM_VOICE_MAX_SEC) {
            queueMicrotask(() => stopVoiceRecordingToReview());
          }
          return next;
        });
      }, 1000);
    });
  };

  const toggleVoiceRecordingPause = () => {
    const rec = mediaRecorderRef.current;
    if (!rec) return;
    if (rec.state === 'recording') {
      try {
        rec.pause();
        setRecordingPaused(true);
        clearRecordingTimer();
      } catch {
        // ignore
      }
    } else if (rec.state === 'paused') {
      try {
        rec.resume();
        setRecordingPaused(false);
        clearRecordingTimer();
        recordingTickRef.current = setInterval(() => {
          setRecordingElapsedSec((s) => {
            const next = s + 1;
            if (next >= DM_VOICE_MAX_SEC) queueMicrotask(() => stopVoiceRecordingToReview());
            return next;
          });
        }, 1000);
      } catch {
        // ignore
      }
    }
  };

  const discardVoiceReview = () => {
    if (voiceReviewAttachment?.url?.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(voiceReviewAttachment.url);
      } catch {
        // ignore
      }
    }
    setVoiceReviewAttachment(null);
    setVoiceReviewPlaying(false);
    try {
      voiceReviewAudioRef.current?.pause();
    } catch {
      // ignore
    }
    voiceReviewAudioRef.current = null;
  };

  const toggleVoiceReviewPlayback = () => {
    const u = voiceReviewAttachment?.url;
    if (!u) return;
    if (voiceReviewPlaying) {
      voiceReviewAudioRef.current?.pause();
      setVoiceReviewPlaying(false);
      return;
    }
    if (voiceReviewAudioRef.current) {
      voiceReviewAudioRef.current.pause();
    }
    const a = new Audio(u);
    voiceReviewAudioRef.current = a;
    a.onended = () => setVoiceReviewPlaying(false);
    a.play().then(() => setVoiceReviewPlaying(true)).catch(() => setVoiceReviewPlaying(false));
  };

  const sendVoiceReview = async () => {
    if (!voiceReviewAttachment || !isInternalChat) return;
    const att = voiceReviewAttachment;
    try {
      const dataUrl = await blobUrlToDataUrl(att.url);
      if (dataUrl.length > 2_000_000) {
        addSystemNote('Voice message is too large. Try a shorter recording.');
        return;
      }
      const resolved: MessageAttachment = { ...att, url: dataUrl };
      if (isDmPage && dmSlug) {
        await sendMessageBySlug(
          dmSlug,
          encodeDmMessagePayload({ text: '', attachment: resolved }),
          replyingTo?.id,
        );
      } else if (isTeamChannel && teamId) {
        sendTypingWs(false);
        const payloadJson = encodeTeamMessageContent({
          text: '',
          attachment: resolved,
          replyTo: replyingTo ?? undefined,
          mentions: mentionIdsRef.current.size > 0 ? Array.from(mentionIdsRef.current) : undefined,
        });
        const body: Record<string, number | string | boolean> = {
          tenant_id: Number(TENANT_ID),
          content: typeof payloadJson === 'string' ? payloadJson : String(payloadJson ?? ''),
        };
        if (broadcastMode) {
          body.posted_by_admin = true;
        } else {
          const senderId = Number.parseInt(String(getCurrentAgent()?.id ?? ''), 10);
          if (!Number.isFinite(senderId) || senderId < 1) throw new Error('Agent not found');
          body.sender_agent_id = senderId;
        }
        if (typeof replyingTo?.id === 'number' && replyingTo.id > 0) {
          body.reply_to_message_id = replyingTo.id;
        }
        const res = await fetch(`${API_BASE}/api/teams/${Number(teamId)}/channel/messages`, {
          method: 'POST',
          headers: teamChannelJsonHeaders(),
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Failed to send team message');
        const saved = (await res.json()) as TeamChannelMessageRow;
        const mapped = mapTeamRowToMessage(saved);
        setMessages((prev) => {
          const idx = prev.findIndex((x) => x.id === mapped.id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = mapped;
            return next;
          }
          return [...prev, mapped].sort((a, b) => a.id - b.id);
        });
        mentionIdsRef.current = new Set();
      }
    } catch {
      addSystemNote('Voice message failed to send. Please try again.');
      return;
    }
    if (att.url.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(att.url);
      } catch {
        // ignore
      }
    }
    setVoiceReviewAttachment(null);
    setVoiceReviewPlaying(false);
    voiceReviewAudioRef.current = null;
    setReplyingTo(null);
  };

  useEffect(() => {
    return () => {
      clearRecordingTimer();
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        // ignore
      }
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const ALLOWED_FILE_EXTENSIONS = ['.pdf', '.csv', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.ppt', '.pptx'];
  const ALLOWED_FILE_TYPES = [
    'application/pdf',
    'text/csv',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  ];

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>, type: 'file' | 'photo') => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (type === 'photo') {
      const lowerName = file.name.toLowerCase();
      const isHeicLike = lowerName.endsWith('.heic') || lowerName.endsWith('.heif');
      if (!file.type.startsWith('image/') && !isHeicLike) {
        return;
      }
    } else {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      const allowed =
        ALLOWED_FILE_EXTENSIONS.includes(ext) || ALLOWED_FILE_TYPES.includes(file.type);
      if (!allowed) {
        return;
      }
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = typeof reader.result === 'string' ? reader.result : '';
      setPendingAttachment({
        type,
        name: file.name,
        url: dataUrl,
      });
      setShowAttachmentMenu(false);
      e.target.value = '';
    };
    reader.readAsDataURL(file);
  };

  const EMOJI_LIST = ['😀', '😂', '❤️', '👍', '👋', '🎉', '🔥', '✨', '😊', '🥳', '🙏', '💯', '😍', '🤔', '👏', '😎', '💪', '🌸', '⭐', '📷'];

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setInputValue(v);
    if (isTeamChannel && !readOnly) {
      sendTypingWs(true);
      if (typingStopTimerRef.current) clearTimeout(typingStopTimerRef.current);
      typingStopTimerRef.current = setTimeout(() => {
        typingStopTimerRef.current = null;
        sendTypingWs(false);
      }, 2000);
    }
    if (!mentionComposerEnabled) {
      setShowMentionDropdown(false);
      return;
    }
    const start = e.target.selectionStart ?? v.length;
    const textToCursor = v.slice(0, start);
    const lastAt = textToCursor.lastIndexOf('@');
    if (lastAt >= 0) {
      const afterAt = textToCursor.slice(lastAt + 1);
      if (!/\s/.test(afterAt)) {
        setMentionFilter(afterAt);
        mentionAnchorRef.current = lastAt;
        setShowMentionDropdown(true);
        setMentionIndex(0);
        return;
      }
    }
    setShowMentionDropdown(false);
  };

  const insertMention = (name: string, agentId?: string) => {
    const start = mentionAnchorRef.current;
    const cursor = inputRef.current?.selectionStart ?? inputValue.length;
    const newValue =
      inputValue.slice(0, start) + `@${name} ` + inputValue.slice(cursor);
    setInputValue(newValue);
    setShowMentionDropdown(false);
    if (agentId) {
      const aid = Number.parseInt(agentId, 10);
      if (Number.isFinite(aid) && aid >= 1) mentionIdsRef.current.add(aid);
    }
    setTimeout(() => {
      inputRef.current?.focus();
      const pos = start + name.length + 2;
      inputRef.current?.setSelectionRange(pos, pos);
    }, 0);
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showMentionDropdown && mentionCandidatesList.length > 0) {
      if (e.key === 'Escape') {
        setShowMentionDropdown(false);
        e.preventDefault();
        return;
      }
      if (e.key === 'ArrowDown') {
        setMentionIndex((i) => (i + 1) % mentionCandidatesList.length);
        e.preventDefault();
        return;
      }
      if (e.key === 'ArrowUp') {
        setMentionIndex((i) => (i - 1 + mentionCandidatesList.length) % mentionCandidatesList.length);
        e.preventDefault();
        return;
      }
      if (e.key === 'Enter' && mentionCandidatesList.length > 0) {
        const pick = mentionCandidatesList[mentionIndex];
        insertMention(pick.name, pick.agentId || undefined);
        e.preventDefault();
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const showThreadSearchBar =
    (isInboxPage && hasSelectedConversation && !isInternalChat) ||
    (isInternalChat && (isTeamChannel || isDmPage));

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="h-chat-header border-b border-border px-6 flex items-center justify-between bg-white shrink-0">
        <div
          className={isTeamChannel ? 'cursor-pointer' : isDmPage ? 'cursor-pointer' : undefined}
          onClick={isTeamChannel ? () => setShowGroupInfo(true) : isDmPage ? () => setShowAgentProfile(true) : undefined}
        >
          {isInternalChat && !isTeamChannel && !isDmPage && !readOnly && (
            <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-primary border border-primary rounded px-2 py-0.5 mb-1.5">
              Internal Chat
            </span>
          )}
          <h3 className="font-medium text-text-primary">
            {headerTitle}
          </h3>
          <p className="text-xs text-text-secondary">
            {headerSubtitle}
          </p>
        </div>
        <div className="relative flex items-center gap-2">
          {!isInternalChat && (
            <span className="text-xs px-2 py-1 bg-status-success text-white rounded">WhatsApp</span>
          )}
          {!isTeamChannel && !isDmPage && (
            <>
              <button
                type="button"
                disabled={isInboxPage && !hasSelectedConversation}
                onClick={() => {
                  if (isInboxPage && !hasSelectedConversation) return;
                  setShowMoreMenu((v) => !v);
                }}
                className="text-text-secondary hover:text-text-primary p-1.5 rounded disabled:opacity-40 disabled:cursor-not-allowed"
                aria-label="More options"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z"
                  />
                </svg>
              </button>

              {showMoreMenu && (
                <>
                  <div className="fixed inset-0 z-10" onClick={closeMenus} aria-hidden />
                  <div className="absolute right-0 top-full mt-2 w-56 bg-white border border-border rounded-lg shadow-xl z-20 py-1">
                    <button
                      type="button"
                      onClick={() => {
                        const content = 'Conversation sent back to AI bot.';
                        if (inboxConv?.selectedId != null) {
                          const now = new Date();
                          const systemMsg: Message = {
                            id: Math.max(0, ...messages.map((m) => m.id)) + 1,
                            content,
                            sender: 'ai',
                            senderName: 'System',
                            timestamp: now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
                            sentAt: now.toISOString(),
                          };
                          inboxConv.appendMessage(inboxConv.selectedId, systemMsg as InboxMessage);
                          inboxConv.sendConversationToAI(inboxConv.selectedId);
                          setMessages((prev) => [...prev, systemMsg]);
                        } else {
                          addSystemNote(content);
                        }
                        closeMenus();
                      }}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-panel text-text-primary"
                    >
                      <Bot className="w-4 h-4" />
                      Send back to AI
                    </button>
                    {showTransferControls && hasSelectedConversation && (
                      <button
                        type="button"
                        onClick={() => {
                          closeMenus();
                          setTransferTargetId(null);
                          setTransferTargetName('');
                          setTransferDescription('');
                          setShowTransferModal(true);
                        }}
                        className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-panel text-text-primary"
                      >
                        <UserPlus className="w-4 h-4" />
                        Transfer
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        if (hasSelectedConversation && inboxConv?.selectedId != null) {
                          const now = new Date();
                          const systemMsg: Message = {
                            id: Math.max(0, ...messages.map((m) => m.id)) + 1,
                            content: 'Conversation closed by agent.',
                            sender: 'ai',
                            senderName: 'System',
                            timestamp: now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
                            sentAt: now.toISOString(),
                          };
                          inboxConv.appendMessage(inboxConv.selectedId, systemMsg as InboxMessage);
                          setMessages((prev) => [...prev, systemMsg]);
                          inboxConv.closeConversation(inboxConv.selectedId);
                        } else {
                          addSystemNote('Conversation closed by agent.');
                        }
                        closeMenus();
                      }}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-panel text-status-error"
                    >
                      <AlertCircle className="w-4 h-4" />
                      Close chat
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {threadSearchOpen && showThreadSearchBar && (
        <div className="shrink-0 border-b border-border bg-[#f7f8fa]">
          <div className="flex items-center gap-2 px-4 py-2">
            <Search className="h-4 w-4 shrink-0 text-[#667781]" aria-hidden />
            <input
              type="search"
              autoFocus
              className="min-w-0 flex-1 rounded-lg border border-black/[0.08] bg-white px-3 py-2 text-sm text-[#111b21] outline-none focus:border-[#53bdeb]"
              placeholder="Search in this chat (⌘F / Ctrl+F)"
              value={threadSearchQuery}
              onChange={(e) => setThreadSearchQuery(e.target.value)}
              aria-label="Search messages in thread"
            />
            <button
              type="button"
              className="shrink-0 text-sm font-medium text-primary"
              onClick={() => {
                setThreadSearchOpen(false);
                setThreadSearchQuery('');
              }}
            >
              Close
            </button>
          </div>
          {threadSearchTrim.length > 0 && (
            <div className="max-h-28 overflow-y-auto border-t border-black/[0.06] px-2 py-1">
              {threadSearchMatches.length === 0 ? (
                <p className="px-2 py-2 text-xs text-[#667781]">No matches</p>
              ) : (
                threadSearchMatches.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className="w-full truncate rounded-md px-2 py-1.5 text-left text-xs text-[#111b21] hover:bg-white"
                    onClick={() => {
                      scrollToMessage(m.id);
                      setThreadSearchOpen(false);
                    }}
                  >
                    {m.content.slice(0, 120)}
                    {m.content.length > 120 ? '…' : ''}
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* Transfer chat modal */}
      {showTransferModal && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40"
            onClick={() => setShowTransferModal(false)}
            aria-hidden
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <div
              className="bg-white rounded-xl border border-border shadow-xl w-full max-w-md pointer-events-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                <h2 className="text-lg font-semibold text-text-primary">Transfer chat</h2>
                <button
                  type="button"
                  onClick={() => setShowTransferModal(false)}
                  className="p-1.5 rounded-lg hover:bg-panel text-text-muted"
                  aria-label="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1.5">Transfer to</label>
                  <select
                    value={transferTargetId ?? ''}
                    onChange={(e) => {
                      const id = e.target.value || null;
                      setTransferTargetId(id);
                      const opt = transferTargetOptions.find((o) => o.id === id);
                      setTransferTargetName(opt?.name ?? '');
                    }}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary text-text-primary bg-white"
                  >
                    <option value="">Select a team member</option>
                    {transferTargetOptions.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                  {transferTargetOptions.length === 0 && (
                    <p className="text-xs text-text-muted mt-1">No other team members found. Add members in Admin → Teams.</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1.5">Note (optional)</label>
                  <textarea
                    value={transferDescription}
                    onChange={(e) => setTransferDescription(e.target.value)}
                    placeholder="e.g. Customer asked for a callback, please follow up."
                    rows={3}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary text-text-primary placeholder-text-muted resize-none"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowTransferModal(false)}
                    className="px-4 py-2 rounded-lg border border-border text-text-primary hover:bg-panel"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={!transferTargetId}
                    onClick={() => {
                      if (!transferTargetId || !transferTargetName || !inboxConv?.selectedId) return;
                      const convId = inboxConv.selectedId;
                      const conv = selectedConv;
                      const customerName = conv?.customerName ?? 'Customer';
                      const now = new Date();
                      const noteText = transferDescription.trim()
                        ? `Conversation transferred to ${transferTargetName} by ${agentFullName}. ${transferDescription}`
                        : `Conversation transferred to ${transferTargetName} by ${agentFullName}.`;
                      const systemMsg: Message = {
                        id: Math.max(0, ...messages.map((m) => m.id)) + 1,
                        content: noteText,
                        sender: 'ai',
                        senderName: 'System',
                        timestamp: now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
                        sentAt: now.toISOString(),
                      };
                      inboxConv.appendMessage(convId, systemMsg as InboxMessage);
                      setMessages((prev) => [...prev, systemMsg]);
                      inboxConv.transferConversation(convId, transferTargetId, transferTargetName);
                      notifications.addNotification({
                        type: 'chat_transfer',
                        message: `Chat transferred to you by ${agentFullName}`,
                        description: transferDescription.trim() || undefined,
                        fromAgentId: getCurrentAgent()?.id,
                        fromAgentName: agentFullName,
                        toAgentId: transferTargetId,
                        toAgentName: transferTargetName,
                        conversationId: convId,
                        conversationCustomerName: customerName,
                      });
                      setShowTransferModal(false);
                      setTransferTargetId(null);
                      setTransferTargetName('');
                      setTransferDescription('');
                    }}
                    className="px-4 py-2 rounded-lg bg-primary text-white hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Transfer
                  </button>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Messages Container */}
      <div
        ref={scrollContainerRef}
        className="chat-messages-scroll chat-wallpaper flex-1 overflow-y-auto p-6 space-y-4 relative"
      >
        {showChatThreadSkeleton && (
          <div className="space-y-4 max-w-2xl mx-auto py-2" aria-busy aria-label="Loading messages">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className={`flex w-full ${i % 2 === 0 ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className="h-11 w-[min(100%,280px)] rounded-2xl bg-[#f0f2f5] animate-pulse"
                  style={{ animationDelay: `${i * 70}ms` }}
                />
              </div>
            ))}
          </div>
        )}
        {!showChatThreadSkeleton && isTeamChannel && teamLoadingOlder && (
          <div className="flex justify-center py-2 shrink-0">
            <span className="text-xs text-[#667781]">Loading older messages…</span>
          </div>
        )}
        {!showChatThreadSkeleton && isDmPage && loadingOlderDmSlug === dmSlug && (
          <div className="flex justify-center py-2 shrink-0">
            <span className="text-xs text-[#667781]">Loading older messages…</span>
          </div>
        )}
        {!showChatThreadSkeleton && isInboxPage && !isInternalChat && inboxLoadingOlder && (
          <div className="flex justify-center py-2 shrink-0">
            <span className="text-xs text-[#667781]">Loading older messages…</span>
          </div>
        )}
        {!showChatThreadSkeleton && selectedConv?.reopenedAt && selectedConv.closedAt && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            You closed this conversation on {selectedConv.closedAt}. The customer has messaged again.
          </div>
        )}
        {!showChatThreadSkeleton && stickyDate && (
          <div className="sticky top-0 z-10 flex justify-center py-2 pointer-events-none">
            <span className="rounded-full border border-black/[0.06] bg-white/90 px-3 py-1.5 text-xs font-medium text-[#54656f] shadow-sm backdrop-blur-sm">
              {formatDateLabel(stickyDate + 'T12:00:00')}
            </span>
          </div>
        )}
        {!showChatThreadSkeleton &&
          unifiedGroups.map((group) => (
          <div key={group.dateKey} className="space-y-4">
            <div
              data-date-key={group.dateKey}
              className="flex justify-center py-2"
            >
              <span className="rounded-full border border-black/[0.06] bg-white/90 px-3 py-1.5 text-xs font-medium text-[#54656f] shadow-sm backdrop-blur-sm">
                {group.label}
              </span>
            </div>
            {group.events.map((ev) => {
              const text =
                ev.type === 'member_removed'
                  ? `${ev.memberName} removed from the Team`
                  : ev.type === 'member_transferred' && ev.targetTeamName
                    ? `${ev.memberName} transferred to ${ev.targetTeamName}`
                    : ev.type === 'member_added'
                      ? `${ev.memberName} added to the Team`
                      : '';
              if (!text) return null;
              return (
                <div key={ev.id} className="flex justify-center py-1">
                  <span className="text-xs text-text-muted bg-panel/80 rounded-full px-3 py-1.5">
                    {text}
                  </span>
                </div>
              );
            })}
            {group.messages.map((message, mi) => {
              const prevInGroup = mi > 0 ? group.messages[mi - 1] : null;
              const gapMin =
                prevInGroup?.sentAt && message.sentAt
                  ? (new Date(message.sentAt).getTime() - new Date(prevInGroup.sentAt).getTime()) /
                    60000
                  : Infinity;
              const groupWithPrev =
                !!prevInGroup &&
                prevInGroup.sender === message.sender &&
                prevInGroup.senderName === message.senderName &&
                gapMin <= 5;
              const isSystemMessage =
                message.senderName === 'System' ||
                message.content.startsWith('Conversation sent back to AI') ||
                message.content.startsWith('Conversation closed by agent') ||
                message.content.includes('Conversation transferred to');
              if (isSystemMessage) {
                return (
                  <div key={message.id} id={`message-${message.id}`} className="flex justify-center py-2">
                    <span className="text-xs text-text-muted italic max-w-[85%] text-center">
                      {message.content}
                    </span>
                  </div>
                );
              }

              const outgoing = isOutgoingMessage(message);
              const receiptPeers = isTeamChannel && outgoing ? getReceiptPeersForMessage(message) : [];
              const sum = message.teamReceiptSummary;
              const rc = sum?.recipient_count ?? 0;
              const peersLen = receiptPeers.length;
              const useReceiptSummary = Boolean(sum && rc > 0 && (peersLen === 0 || rc === peersLen));
              const allDeliveredReceipt =
                useReceiptSummary && sum ? sum.delivered_count >= rc : true;
              const allReadReceipt =
                useReceiptSummary && sum
                  ? sum.read_count >= rc
                  : receiptPeers.length === 0 ||
                    receiptPeers.every((p) => (memberReadStates[String(p.id)] ?? 0) >= message.id);
              const anyReadReceipt =
                useReceiptSummary && sum
                  ? sum.read_count > 0
                  : receiptPeers.some(
                      (p) => (memberReadStates[String(p.id)] ?? 0) >= message.id,
                    );
              const isStarred = starredIds.includes(message.id);
              const showMenu = activeMessageMenuId === message.id;
              const showReactions = activeReactionPickerId === message.id;
              const reactionEmojis = ['👍', '❤️', '😂', '😮', '😢', '🙏', '👏', '😁'];
              const reactionList = message.reactions ?? [];
              const myReaction = reactionList.find((r) => r.userId === reactionActorId)?.emoji;
              const aggregated = Object.entries(
                reactionList.reduce<Record<string, number>>((acc, r) => {
                  acc[r.emoji] = (acc[r.emoji] ?? 0) + 1;
                  return acc;
                }, {}),
              ).map(([emoji, count]) => ({ emoji, count }));
              const showReactionDetail = reactionDetailMessageId === message.id;
              const emojiOnly = !message.attachment && isEmojiOnly(message.content);
              const reactionRowsFiltered =
                reactionDetailFilter === 'all'
                  ? reactionList
                  : reactionList.filter((r) => r.emoji === reactionDetailFilter);

              return (
                <div
                  key={message.id}
                  id={`message-${message.id}`}
                  className={`group/message flex w-full items-end gap-1.5 ${outgoing ? 'justify-end' : 'justify-start'}`}
                >
                  {(isTeamChannel || (isInboxPage && !isInternalChat)) && !outgoing && (
                    <div
                      className={`mb-1 flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-white text-sm font-semibold text-[#54656f] shadow-sm ring-1 ring-black/[0.06] ${
                        groupWithPrev ? 'invisible pointer-events-none' : ''
                      }`}
                    >
                      {isTeamChannel && message.senderName === 'You' && agentAvatarUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={agentAvatarUrl} alt="" className="h-full w-full object-cover" />
                      ) : (
                        message.senderName.charAt(0)
                      )}
                    </div>
                  )}
                  <div
                    className={`relative flex max-w-[85%] min-w-0 flex-col ${outgoing ? 'items-end' : 'items-start'}`}
                  >
                    <div
                      className={`relative min-w-[8rem] max-w-message-bubble rounded-2xl px-2.5 pb-1.5 pt-2 pr-9 ${getMessageStyle(message, outgoing)}`}
                    >
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() =>
                            setActiveMessageMenuId((current) =>
                              current === message.id ? null : message.id,
                            )
                          }
                          className="absolute right-1.5 top-1.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-[#54656f] opacity-90 transition-colors hover:bg-black/[0.08]"
                          aria-label="Message options"
                        >
                          <ChevronDown className="h-4 w-4" />
                        </button>
                      )}

                      <div className="min-w-0 space-y-1 pr-0.5">
                        {message.replyTo && (
                          <button
                            type="button"
                            onClick={() => scrollToMessage(message.replyTo!.id)}
                            className={`mb-1.5 w-full cursor-pointer rounded-md border-l-[3px] border-[#53bdeb] py-1.5 pl-2 text-left ${
                              outgoing ? 'bg-[#00000008] hover:bg-[#0000000d]' : 'bg-[#f0f2f5] hover:bg-[#e9edef]'
                            }`}
                            title="Jump to original message"
                          >
                            <p className="text-xs font-semibold text-[#53bdeb]">{message.replyTo.senderName}</p>
                            <p
                              className="max-w-full truncate text-xs text-[#667781]"
                              title={message.replyTo.content}
                            >
                              {message.replyTo.content}
                            </p>
                          </button>
                        )}
                        {!outgoing && !groupWithPrev && (
                          <p
                            className={`mb-0.5 text-[13px] font-semibold ${whatsappSenderNameClass(message.senderName)}`}
                          >
                            {message.senderName}
                          </p>
                        )}
                        {message.attachment && (
                          <div
                            className={`mb-2 overflow-hidden rounded-lg ${outgoing ? 'bg-black/[0.04]' : 'bg-black/[0.04]'}`}
                          >
                            {message.attachment.type === 'photo' && (
                              isHeicLikeAttachment(message.attachment) ? (
                                <a
                                  href={message.attachment.url}
                                  download={message.attachment.name}
                                  className="flex items-center gap-2 rounded-lg px-2 py-2 text-[#111b21] hover:bg-black/[0.04]"
                                >
                                  <ImageIcon className="h-5 w-5 flex-shrink-0" />
                                  <span className="truncate text-sm">{message.attachment.name}</span>
                                </a>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => setPreviewImageSrc(message.attachment?.url || null)}
                                  className="block max-w-full text-left"
                                >
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img
                                    src={message.attachment.url}
                                    alt={message.attachment.name}
                                    className="max-h-48 max-w-full rounded-lg object-cover"
                                  />
                                </button>
                              )
                            )}
                            {message.attachment.type === 'file' && (
                              <a
                                href={message.attachment.url}
                                download={message.attachment.name}
                                className="flex items-center gap-2 rounded-lg px-2 py-2 text-[#111b21] hover:bg-black/[0.04]"
                              >
                                <FileText className="h-5 w-5 flex-shrink-0" />
                                <span className="truncate text-sm">{message.attachment.name}</span>
                              </a>
                            )}
                            {message.attachment.type === 'voice' && (
                              <div className="flex items-center gap-2 py-1 text-[#111b21]">
                                <div className="flex min-w-0 flex-1 items-center gap-2">
                                  <div className="relative flex-shrink-0">
                                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-black/10">
                                      <Mic className="h-4 w-4 text-[#54656f]" />
                                    </div>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      toggleVoicePlayback(
                                        message.id,
                                        message.attachment!.url,
                                        message.attachment!.durationSeconds ?? 0,
                                      )
                                    }
                                    className="flex-shrink-0 rounded-full p-1 text-[#111b21] hover:bg-black/10"
                                    aria-label={playingVoiceId === message.id ? 'Pause' : 'Play voice message'}
                                  >
                                    {playingVoiceId === message.id ? (
                                      <Pause className="h-5 w-5" fill="currentColor" />
                                    ) : (
                                      <Play className="h-5 w-5" fill="currentColor" />
                                    )}
                                  </button>
                                  <div className="flex min-w-0 flex-1 items-center gap-1.5">
                                    <div className="min-w-[4rem] flex-1 overflow-hidden rounded-full bg-black/15 h-1.5">
                                      <div
                                        className="h-full rounded-full bg-[#53bdeb] transition-all duration-150"
                                        style={{ width: `${((voiceProgress[message.id] ?? 0) * 100).toFixed(1)}%` }}
                                      />
                                    </div>
                                    <div className="flex flex-shrink-0 gap-0.5">
                                      {VOICE_WAVEFORM_BARS.map((h, i) => (
                                        <div
                                          key={i}
                                          className="w-0.5 rounded-full bg-[#8696a0]"
                                          style={{ height: `${(h / 100) * 12}px`, minHeight: 4 }}
                                        />
                                      ))}
                                    </div>
                                  </div>
                                </div>
                                <span className="flex-shrink-0 text-xs text-[#667781]">
                                  {formatVoiceDuration(message.attachment.durationSeconds ?? 0)}
                                </span>
                              </div>
                            )}
                          </div>
                        )}
                        {message.sendFailed && (
                          <p className="mb-1 text-xs font-medium text-status-error">Failed to send</p>
                        )}
                        {message.deletedForEveryone || message.content === '[Message deleted]' ? (
                          <p className="whitespace-pre-wrap text-sm italic text-[#667781]">
                            This message was deleted.
                          </p>
                        ) : (
                          <p
                            className={`whitespace-pre-wrap break-words leading-relaxed text-[#111b21] ${emojiOnly ? 'text-5xl' : 'text-sm'}`}
                          >
                            {isTeamChannel ? renderTeamMessageBody(message.content) : message.content}
                          </p>
                        )}
                        <div className="mt-1 flex flex-wrap items-center justify-end gap-x-2 gap-y-0.5">
                          {message.editedAt && (
                            <span className="text-[10px] text-[#667781]">(edited)</span>
                          )}
                          <span className="text-[11px] text-[#667781]">
                            {formatMessageTime(message.sentAt, message.timestamp)}
                          </span>
                          {((isInboxPage && !isInternalChat) || (isInternalChat && isDmPage)) &&
                            outgoing &&
                            message.messageStatus && (
                            <span className="inline-flex items-center" aria-hidden>
                              <Check
                                className={`h-3.5 w-3.5 stroke-[2.5] ${
                                  message.messageStatus.delivered || message.messageStatus.read
                                    ? 'text-[#8696a0]'
                                    : 'text-[#8696a0]/70'
                                }`}
                              />
                              {(message.messageStatus.delivered || message.messageStatus.read) && (
                                <Check
                                  className={`-ml-1.5 h-3.5 w-3.5 stroke-[2.5] ${
                                    message.messageStatus.read ? 'text-[#53bdeb]' : 'text-[#8696a0]'
                                  }`}
                                />
                              )}
                            </span>
                          )}
                          {isTeamChannel && outgoing && receiptPeers.length > 0 && (
                            <span className="relative inline-flex items-center">
                              <button
                                type="button"
                                className="inline-flex items-center p-0.5 -m-0.5 rounded hover:bg-black/[0.04]"
                                aria-label="Read receipts"
                                onClick={() =>
                                  setReadReceiptOpenId((id) => (id === message.id ? null : message.id))
                                }
                              >
                                <Check
                                  className={`h-3.5 w-3.5 stroke-[2.5] ${allDeliveredReceipt ? 'text-[#8696a0]' : 'text-[#8696a0]/50'}`}
                                />
                                <Check
                                  className={`-ml-1.5 h-3.5 w-3.5 stroke-[2.5] ${allReadReceipt ? 'text-[#53bdeb]' : anyReadReceipt ? 'text-[#8696a0]' : 'text-[#8696a0]/50'}`}
                                />
                              </button>
                              {readReceiptOpenId === message.id && receiptPeers.length > 0 && (
                                <>
                                  <div
                                    className="fixed inset-0 z-10"
                                    onClick={() => setReadReceiptOpenId(null)}
                                    aria-hidden
                                  />
                                  <div className="absolute right-0 bottom-full z-20 mb-1 w-56 rounded-lg border border-black/[0.08] bg-white py-2 px-2.5 text-left text-xs shadow-lg">
                                    <p className="mb-1 font-semibold text-[#111b21]">Read</p>
                                    <ul className="max-h-24 overflow-y-auto space-y-0.5 text-[#111b21]">
                                      {receiptPeers
                                        .filter((p) => (memberReadStates[String(p.id)] ?? 0) >= message.id)
                                        .map((p) => (
                                          <li key={p.id}>{p.name}</li>
                                        ))}
                                    </ul>
                                    <p className="mt-2 mb-1 font-semibold text-[#111b21]">Not read yet</p>
                                    <ul className="max-h-24 overflow-y-auto space-y-0.5 text-[#667781]">
                                      {receiptPeers
                                        .filter((p) => (memberReadStates[String(p.id)] ?? 0) < message.id)
                                        .map((p) => (
                                          <li key={p.id}>{p.name}</li>
                                        ))}
                                    </ul>
                                  </div>
                                </>
                              )}
                            </span>
                          )}
                          {isTeamChannel && isStarred && (
                            <Star className="h-3 w-3 flex-shrink-0 fill-[#8696a0] text-[#8696a0]" />
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Reaction pill + emoji (WhatsApp-style) */}
                    <div
                      className={`relative z-10 -mt-2 flex items-center gap-1 ${
                        outgoing ? 'mr-0.5 justify-end' : 'ml-0.5 justify-start'
                      }`}
                    >
                      {aggregated.length > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            setReactionDetailFilter('all');
                            setReactionDetailMessageId((id) =>
                              id === message.id ? null : message.id,
                            );
                          }}
                          className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-sm shadow-[0_1px_1px_rgba(11,20,26,0.08)] transition-colors hover:bg-[#f7f8fa]"
                        >
                          {aggregated.map(({ emoji }) => (
                            <span key={emoji} className="leading-none">
                              {emoji}
                            </span>
                          ))}
                          <span className="tabular-nums text-[13px] font-medium text-[#667781]">
                            {reactionList.length}
                          </span>
                        </button>
                      )}
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() => setActiveReactionPickerId(message.id)}
                          className={`flex-shrink-0 rounded-full border p-1 transition-colors ${
                            myReaction
                              ? 'border-[#53bdeb] bg-[#e7f8ff] text-[#111b21]'
                              : 'border-black/[0.08] bg-white text-[#54656f] shadow-sm hover:border-[#53bdeb]/50'
                          }`}
                          aria-label="React"
                        >
                          {myReaction ? (
                            <span className="text-base leading-none">{myReaction}</span>
                          ) : (
                            <Smile className="h-4 w-4" />
                          )}
                        </button>
                      )}
                    </div>

                    {/* Reaction detail: glass popover + filters */}
                    {showReactionDetail && reactionList.length > 0 && (
                      <div
                        className={`absolute bottom-full z-30 mb-2 w-[min(18rem,calc(100vw-2rem))] ${
                          outgoing ? 'right-0' : 'left-0'
                        }`}
                      >
                        <div
                          className="fixed inset-0 z-20"
                          onClick={() => {
                            setReactionDetailMessageId(null);
                            setReactionDetailFilter('all');
                          }}
                          aria-hidden
                        />
                        <div className="relative z-30 overflow-hidden rounded-2xl border border-white/50 bg-white/75 shadow-[0_8px_32px_rgba(11,20,26,0.15)] backdrop-blur-xl">
                          <div className="flex flex-wrap items-center gap-1 border-b border-black/[0.06] px-2 py-2">
                            <button
                              type="button"
                              onClick={() => setReactionDetailFilter('all')}
                              className={`rounded-full px-2.5 py-1 text-[13px] font-medium transition-colors ${
                                reactionDetailFilter === 'all'
                                  ? 'bg-[#e9edef] text-[#111b21]'
                                  : 'text-[#54656f] hover:bg-black/[0.04]'
                              }`}
                            >
                              All {reactionList.length}
                            </button>
                            {aggregated.map(({ emoji, count }) => (
                              <button
                                key={emoji}
                                type="button"
                                onClick={() => setReactionDetailFilter(emoji)}
                                className={`rounded-full px-2 py-1 text-[13px] transition-colors ${
                                  reactionDetailFilter === emoji
                                    ? 'bg-[#e9edef] text-[#111b21]'
                                    : 'text-[#54656f] hover:bg-black/[0.04]'
                                }`}
                              >
                                <span>{emoji}</span>
                                <span className="ml-0.5 text-[#667781]">{count}</span>
                              </button>
                            ))}
                          </div>
                          <div className="max-h-52 overflow-y-auto chat-messages-scroll">
                            {reactionRowsFiltered.map((r, i) => {
                              const isMe = r.userId === reactionActorId;
                              return (
                                <button
                                  key={`${r.userId}-${r.emoji}-${i}`}
                                  type="button"
                                  className="flex w-full items-center gap-3 border-b border-black/[0.05] px-3 py-2.5 text-left last:border-b-0 hover:bg-white/60"
                                  onClick={() => {
                                    if (isMe) addReaction(message.id, r.emoji);
                                  }}
                                >
                                  <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-[#dfe5e7] text-sm font-semibold text-[#54656f]">
                                    {(r.userName === 'You' || r.userName === 'Admin') && agentAvatarUrl ? (
                                      // eslint-disable-next-line @next/next/no-img-element
                                      <img src={agentAvatarUrl} alt="" className="h-full w-full object-cover" />
                                    ) : (
                                      r.userName.charAt(0)
                                    )}
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <p className="truncate text-sm font-semibold text-[#111b21]">{r.userName}</p>
                                    {isMe ? (
                                      <p className="text-xs text-[#667781]">Click to remove</p>
                                    ) : (
                                      <p className="text-xs text-[#667781]">{formatReactionTime(r.reactedAt)}</p>
                                    )}
                                  </div>
                                  <span className="flex-shrink-0 text-xl">{r.emoji}</span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                        <div
                          className={`pointer-events-none absolute -bottom-1 h-2.5 w-2.5 rotate-45 border-b border-r border-black/[0.08] bg-white/80 backdrop-blur-md ${
                            outgoing ? 'right-8' : 'left-8'
                          }`}
                          aria-hidden
                        />
                      </div>
                    )}

                    {!readOnly && showMenu && (
                      <div
                        className={`absolute z-20 w-52 rounded-xl border border-black/[0.08] bg-white py-1 text-sm shadow-[0_4px_24px_rgba(11,20,26,0.12)] ${
                          outgoing
                            ? dropdownPlaceAbove
                              ? 'bottom-full right-0 mb-1'
                              : 'right-full top-0 mr-2'
                            : dropdownPlaceAbove
                              ? 'bottom-full left-0 mb-1'
                              : 'left-0 top-full mt-1'
                        }`}
                      >
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                          onClick={() => {
                            setReplyingTo({
                              id: message.id,
                              senderName: message.senderName,
                              content: message.content,
                            });
                            setActiveMessageMenuId(null);
                          }}
                        >
                          <CornerDownLeft className="h-4 w-4 text-[#54656f]" />
                          Reply
                        </button>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                          onClick={() => setActiveReactionPickerId(message.id)}
                        >
                          <Smile className="h-4 w-4 text-[#54656f]" />
                          React
                        </button>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                          onClick={() => toggleStar(message.id)}
                        >
                          <Star
                            className={`h-4 w-4 ${
                              isStarred ? 'fill-[#53bdeb] text-[#53bdeb]' : 'text-[#54656f]'
                            }`}
                          />
                          {isStarred ? 'Unstar' : 'Star'}
                        </button>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                          onClick={() => {
                            if (navigator.clipboard?.writeText) {
                              void navigator.clipboard
                                .writeText(message.content)
                                .then(() => flashCopyToast())
                                .catch(() => undefined);
                            }
                            setActiveMessageMenuId(null);
                          }}
                        >
                          <Copy className="h-4 w-4 text-[#54656f]" />
                          Copy
                        </button>
                        {isInboxPage && !isInternalChat && message.sendFailed && (
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                            onClick={() => {
                              retryFailedInboxSend(message);
                              setActiveMessageMenuId(null);
                            }}
                          >
                            <CornerDownLeft className="h-4 w-4 text-[#54656f]" />
                            Retry send
                          </button>
                        )}
                        {isInboxPage &&
                          !isInternalChat &&
                          outgoing &&
                          message.sender === 'agent' &&
                          !message.sendFailed &&
                          !message.deletedForEveryone &&
                          message.content !== '[Message deleted]' && (
                            <button
                              type="button"
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                              onClick={() => {
                                setThreadMessageEdit({ source: 'inbox', id: message.id, text: message.content });
                                setActiveMessageMenuId(null);
                              }}
                            >
                              <Pencil className="h-4 w-4 text-[#54656f]" />
                              Edit
                            </button>
                          )}
                        {isInternalChat &&
                          isDmPage &&
                          outgoing &&
                          !message.deletedForEveryone &&
                          !message.attachment && (
                            <button
                              type="button"
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                              onClick={() => {
                                setThreadMessageEdit({ source: 'dm', id: message.id, text: message.content });
                                setActiveMessageMenuId(null);
                              }}
                            >
                              <Pencil className="h-4 w-4 text-[#54656f]" />
                              Edit
                            </button>
                          )}
                        {isTeamChannel &&
                          isInternalChat &&
                          !readOnly &&
                          outgoing &&
                          !message.deletedForEveryone &&
                          !message.attachment && (
                            <button
                              type="button"
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                              onClick={() => {
                                setThreadMessageEdit({ source: 'team', id: message.id, text: message.content });
                                setActiveMessageMenuId(null);
                              }}
                            >
                              <Pencil className="h-4 w-4 text-[#54656f]" />
                              Edit
                            </button>
                          )}
                        {outgoing && (
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 px-3 py-2 text-left text-[#111b21] hover:bg-[#f0f2f5]"
                            onClick={() => {
                              setMessageInfoId(message.id);
                              setActiveMessageMenuId(null);
                            }}
                          >
                            <Info className="h-4 w-4 text-[#54656f]" />
                            Info
                          </button>
                        )}
                        <div className="my-1 border-t border-black/[0.06]" />
                        {outgoing ? (
                          <>
                            <button
                              type="button"
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-status-error hover:bg-red-50"
                              onClick={() => {
                                void deleteForMe(message.id);
                              }}
                            >
                              <Trash2 className="h-4 w-4" />
                              Delete for me
                            </button>
                            {(!isInboxPage || isInternalChat || message.sender === 'agent') && (
                              <button
                                type="button"
                                className="flex w-full items-center gap-2 px-3 py-2 text-left text-status-error hover:bg-red-50"
                                onClick={() => {
                                  void deleteMessage(message.id);
                                }}
                              >
                                <Trash2 className="h-4 w-4" />
                                Delete for everyone
                              </button>
                            )}
                          </>
                        ) : (
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 px-3 py-2 text-left text-status-error hover:bg-red-50"
                            onClick={() => {
                              void deleteForMe(message.id);
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                            Delete for me
                          </button>
                        )}
                      </div>
                    )}

                    {!readOnly && showReactions && (
                      <div
                        className={`absolute z-40 mt-2 w-72 rounded-2xl border border-white/60 bg-white/90 p-3 shadow-[0_8px_32px_rgba(11,20,26,0.14)] backdrop-blur-xl ${
                          outgoing ? 'right-0' : 'left-0'
                        }`}
                      >
                        <p className="mb-2 text-xs text-[#667781]">
                          Tap to react · tap again on yours to remove
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {reactionEmojis.map((emoji) => {
                            const isSelected = myReaction === emoji;
                            return (
                              <button
                                key={emoji}
                                type="button"
                                className={`flex h-9 w-9 items-center justify-center rounded-full text-xl transition-colors ${
                                  isSelected
                                    ? 'border-2 border-[#53bdeb] bg-[#e7f8ff]'
                                    : 'hover:bg-[#f0f2f5]'
                                }`}
                                onClick={() => addReaction(message.id, emoji)}
                              >
                                {emoji}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                  {((isTeamChannel && outgoing) || (isInboxPage && !isInternalChat && outgoing)) && (
                    <div
                      className={`mb-1 flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-white text-sm font-semibold text-[#54656f] shadow-sm ring-1 ring-black/[0.06] ${
                        isInboxPage && !isInternalChat && groupWithPrev ? 'invisible pointer-events-none' : ''
                      }`}
                    >
                      {isTeamChannel && (message.postedByAdmin || message.senderName === 'Admin') ? (
                        'A'
                      ) : agentAvatarUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={agentAvatarUrl} alt="" className="h-full w-full object-cover" />
                      ) : (
                        (agentFullName || 'You').charAt(0)
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
        {(teamNewBelowOpen && isTeamChannel) ||
        (dmNewBelowOpen && isDmPage) ||
        (inboxNewBelowOpen && isInboxPage && !isInternalChat) ? (
          <div className="pointer-events-none sticky bottom-2 z-20 flex justify-center py-2">
            <button
              type="button"
              className="pointer-events-auto rounded-full bg-primary px-4 py-2 text-xs font-semibold text-white shadow-lg hover:opacity-95"
              onClick={() => {
                const el = scrollContainerRef.current;
                if (el) el.scrollTop = el.scrollHeight;
                setTeamNewBelowOpen(false);
                setDmNewBelowOpen(false);
                setInboxNewBelowOpen(false);
                teamNearBottomRef.current = true;
                dmNearBottomRef.current = true;
                inboxNearBottomRef.current = true;
                if (isDmPage && dmSlug) clearDmUnread(dmSlug);
                if (isTeamChannel && teamId && !readOnly && viewerAgentId) {
                  const ids = messages.map((m) => m.id);
                  if (ids.length > 0) {
                    const v = Math.max(...ids);
                    void fetch(`${API_BASE}/api/teams/${Number(teamId)}/channel/read-state`, {
                      method: 'POST',
                      headers: teamChannelJsonHeaders(),
                      body: JSON.stringify({ tenant_id: TENANT_ID, last_read_message_id: v }),
                    }).catch(() => undefined);
                  }
                }
              }}
            >
              New messages below
            </button>
          </div>
        ) : null}
      </div>

      {/* Input Area */}
      <div className="flex-shrink-0 border-t border-border bg-white">
        {/* Reply bar when active (hidden in read-only) */}
        {!readOnly && replyingTo && (
          <div className="flex items-center justify-between gap-3 px-4 py-2 bg-panel border-b border-border">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-primary">Replying to {replyingTo.senderName}</p>
              <p className="text-xs text-text-secondary truncate" title={replyingTo.content}>
                {replyingTo.content}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setReplyingTo(null)}
              className="p-1.5 rounded-full hover:bg-white border border-border text-text-muted flex-shrink-0"
              aria-label="Cancel reply"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {!readOnly && voiceReviewAttachment && isInternalChat && (
          <div className="px-4 py-3 bg-panel border-b border-border flex flex-wrap items-center gap-3">
            <Mic className="w-5 h-5 text-primary shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary">Review voice message</p>
              <p className="text-xs text-text-muted">
                {voiceReviewAttachment.durationSeconds ?? 0}s · Play to check, then send or discard
              </p>
            </div>
            <button
              type="button"
              onClick={toggleVoiceReviewPlayback}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium text-text-primary hover:bg-white"
            >
              {voiceReviewPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              {voiceReviewPlaying ? 'Pause' : 'Play'}
            </button>
            <button
              type="button"
              onClick={discardVoiceReview}
              className="rounded-lg border border-border px-3 py-2 text-sm font-medium text-text-secondary hover:bg-white"
            >
              Delete
            </button>
            <button
              type="button"
              onClick={() => void sendVoiceReview()}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90"
            >
              Send voice
            </button>
          </div>
        )}
        
        {/* Pending attachment preview (hidden in read-only) */}
        {!readOnly && pendingAttachment && (
          <div className="px-4 py-2 bg-panel border-b border-border flex items-center justify-between gap-2">
            <span className="text-xs text-text-secondary truncate">
              {pendingAttachment.type === 'photo' && (
                <>
                  <ImageIcon className="w-4 h-4 inline-block mr-1 align-middle" />
                  {pendingAttachment.name}
                </>
              )}
              {pendingAttachment.type === 'file' && (
                <>
                  <FileText className="w-4 h-4 inline-block mr-1 align-middle" />
                  {pendingAttachment.name}
                </>
              )}
              {pendingAttachment.type === 'voice' && (
                <>
                  <Mic className="w-4 h-4 inline-block mr-1 align-middle" />
                  Voice message {pendingAttachment.durationSeconds != null && `(${pendingAttachment.durationSeconds}s)`}
                </>
              )}
            </span>
            <button
              type="button"
              onClick={() => setPendingAttachment(null)}
              className="p-1 rounded-full hover:bg-white text-text-muted"
              aria-label="Remove attachment"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
        
        {isTeamChannel && Object.keys(teamTypers).length > 0 && (
          <div className="px-4 py-1.5 text-xs text-[#667781] border-b border-black/[0.06] bg-[#f7f8fa]">
            {Array.from(new Set(Object.values(teamTypers).map((t) => t.name))).join(', ')}
            {Object.keys(teamTypers).length === 1 ? ' is typing…' : ' are typing…'}
          </div>
        )}

        {/* Input row - fixed height to align bottom separator with 2nd bar (80px) */}
        {(!readOnly || showBroadcastInput) && (
          <div className="flex items-center gap-2 px-4 h-[80px]">
            {!showBroadcastInput && (
              <div className="relative flex-shrink-0">
                <button
                  type="button"
                  onClick={() => { setShowAttachmentMenu((v) => !v); setShowEmojiPicker(false); }}
                  className="text-text-secondary hover:text-primary p-2 rounded-full transition-colors"
                  aria-label="Attach"
                >
                  <Plus className="w-6 h-6" />
                </button>
                {showAttachmentMenu && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setShowAttachmentMenu(false)} aria-hidden />
                    <div className="absolute left-0 bottom-full mb-1 w-52 bg-white border border-border rounded-xl shadow-xl z-20 py-1">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-panel text-left text-sm text-text-primary"
                      >
                        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
                          <FileText className="w-5 h-5 text-primary" />
                        </div>
                        File
                      </button>
                      <button
                        type="button"
                        onClick={() => photoInputRef.current?.click()}
                        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-panel text-left text-sm text-text-primary"
                      >
                        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
                          <ImageIcon className="w-5 h-5 text-primary" />
                        </div>
                        Photos
                      </button>
                    </div>
                  </>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.csv,.doc,.docx,.xls,.xlsx,.txt,.ppt,.pptx,application/pdf,text/csv,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/plain,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation"
                  className="hidden"
                  onChange={(e) => handleFileSelect(e, 'file')}
                />
                <input
                  ref={photoInputRef}
                  type="file"
                  accept="image/*,.heic,.heif,image/heic,image/heif"
                  className="hidden"
                  onChange={(e) => handleFileSelect(e, 'photo')}
                />
              </div>
            )}
            
            <div className="flex-1 min-w-0 relative flex items-center gap-2 border border-border rounded-lg bg-white focus-within:ring-2 focus-within:ring-primary">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={handleInputChange}
                placeholder={
                  mentionComposerEnabled
                    ? 'Type a message... Use @ to mention someone'
                    : replyingTo
                      ? `Reply to ${replyingTo.senderName}...`
                      : 'Type a message...'
                }
                className="flex-1 min-w-0 px-4 py-2.5 focus:outline-none text-sm bg-transparent"
                onKeyDown={handleInputKeyDown}
              />
              
              {mentionComposerEnabled && showMentionDropdown && mentionCandidatesList.length > 0 && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowMentionDropdown(false)}
                    aria-hidden
                  />
                  <div className="absolute left-0 right-0 bottom-full mb-1 max-h-48 overflow-y-auto bg-white border border-border rounded-lg shadow-xl z-20 py-1">
                    {mentionCandidatesList.map((row, i) => (
                      <button
                        key={row.agentId ? `${row.agentId}-${row.name}` : row.name}
                        type="button"
                        className={`w-full px-3 py-2 text-left text-sm hover:bg-panel text-text-primary flex items-center gap-2 ${i === mentionIndex ? 'bg-panel' : ''}`}
                        onClick={() => insertMention(row.name, row.agentId || undefined)}
                      >
                        <User className="w-4 h-4 text-text-muted flex-shrink-0" />
                        {row.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
              
              {!showBroadcastInput && (
                <>
                  <button
                    type="button"
                    onClick={() => { setShowEmojiPicker((v) => !v); setShowAttachmentMenu(false); }}
                    className="p-2 text-text-muted hover:text-primary rounded-full transition-colors flex-shrink-0"
                    aria-label="Emoji"
                  >
                    <Smile className="w-5 h-5" />
                  </button>
                  {showEmojiPicker && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setShowEmojiPicker(false)} aria-hidden />
                      <div className="absolute right-0 bottom-full mb-1 w-64 bg-white border border-border rounded-xl shadow-xl z-20 p-3">
                        <p className="text-xs font-medium text-text-muted mb-2">Emoji</p>
                        <div className="grid grid-cols-5 gap-1">
                          {EMOJI_LIST.map((emoji) => (
                            <button
                              key={emoji}
                              type="button"
                              className="w-9 h-9 flex items-center justify-center text-xl rounded-lg hover:bg-panel"
                              onClick={() => {
                                setInputValue((prev) => prev + emoji);
                                inputRef.current?.focus();
                              }}
                            >
                              {emoji}
                            </button>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </>
              )}
            </div>
            
            {!showBroadcastInput &&
              (isRecording ? (
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    type="button"
                    onClick={cancelVoiceRecording}
                    className="p-2 rounded-full text-text-muted hover:bg-panel hover:text-status-error"
                    aria-label="Cancel recording"
                    title="Cancel"
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                  <span className="tabular-nums text-xs text-text-secondary min-w-[3rem] text-center">
                    {Math.floor(recordingElapsedSec / 60)
                      .toString()
                      .padStart(2, '0')}
                    :{(recordingElapsedSec % 60).toString().padStart(2, '0')}
                  </span>
                  {typeof MediaRecorder !== 'undefined' &&
                    MediaRecorder.prototype != null &&
                    'pause' in MediaRecorder.prototype && (
                      <button
                        type="button"
                        onClick={toggleVoiceRecordingPause}
                        className="p-2 rounded-full text-text-secondary hover:bg-panel text-xs font-medium w-14"
                        aria-label={recordingPaused ? 'Resume recording' : 'Pause recording'}
                      >
                        {recordingPaused ? 'Resume' : 'Pause'}
                      </button>
                    )}
                  <button
                    type="button"
                    onClick={stopVoiceRecordingToReview}
                    className="p-2.5 rounded-full bg-status-error text-white hover:bg-status-error/90 flex-shrink-0"
                    aria-label="Stop and review"
                    title="Stop"
                  >
                    <Square className="w-5 h-5" />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setShowAttachmentMenu(false);
                    setShowEmojiPicker(false);
                    startVoiceRecording();
                  }}
                  className="text-text-secondary hover:text-primary p-2 rounded-full transition-colors flex-shrink-0"
                  aria-label="Voice message"
                >
                  <Mic className="w-6 h-6" />
                </button>
              ))}
            
            <button
              type="button"
              className="bg-primary text-white px-5 py-2.5 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium flex-shrink-0"
              onClick={sendMessage}
            >
              Send
            </button>
          </div>
        )}
      </div>

      {/* Backdrop for menus */}
      {(activeMessageMenuId !== null || activeReactionPickerId !== null) && (
        <div
          className="fixed inset-0 z-10"
          onClick={() => {
            setActiveMessageMenuId(null);
            setActiveReactionPickerId(null);
          }}
        />
      )}

      {copyToastVisible && (
        <div
          className="pointer-events-none fixed bottom-24 left-1/2 z-[60] -translate-x-1/2 rounded-full bg-[#111b21] px-4 py-2 text-sm font-medium text-white shadow-lg"
          role="status"
        >
          Copied!
        </div>
      )}

      {threadMessageEdit && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setThreadMessageEdit(null)}
          aria-modal
        >
          <div
            className="w-full max-w-md rounded-xl border border-border bg-white p-4 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-2 font-semibold text-text-primary">Edit message</h3>
            <textarea
              className="min-h-[100px] w-full resize-y rounded-lg border border-border p-2 text-sm text-text-primary outline-none focus:ring-2 focus:ring-primary"
              value={threadMessageEdit.text}
              onChange={(e) =>
                setThreadMessageEdit({ ...threadMessageEdit, text: e.target.value })
              }
              aria-label="Edited message text"
            />
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-primary hover:bg-panel"
                onClick={() => setThreadMessageEdit(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-dark"
                onClick={() => void submitThreadMessageEdit()}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Message Info Modal */}
      {messageInfoId !== null && (() => {
        const targetMessage = messages.find((m) => m.id === messageInfoId) ?? null;
        const formatReadAt = (d: Date) =>
          `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getFullYear()} ${d.getHours() % 12 || 12}:${d.getMinutes().toString().padStart(2, '0')} ${d.getHours() >= 12 ? 'PM' : 'AM'}`;

        if (isInboxPage && !isInternalChat && targetMessage) {
          const sent = targetMessage.sentAt ? new Date(targetMessage.sentAt) : null;
          const st = targetMessage.messageStatus;
          const sentOk = sent && !Number.isNaN(sent.getTime());
          return (
            <div
              className="fixed inset-0 z-30 flex items-start justify-center bg-black/20 pt-20"
              onClick={() => setMessageInfoId(null)}
            >
              <div
                className="w-full max-w-sm overflow-hidden rounded-xl border border-border bg-white shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between border-b border-border px-4 py-3">
                  <span className="font-semibold text-text-primary">Message info</span>
                  <button
                    type="button"
                    onClick={() => setMessageInfoId(null)}
                    className="rounded-full p-1.5 text-text-muted hover:bg-panel"
                    aria-label="Close"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <div className="max-h-80 space-y-3 overflow-y-auto px-4 py-4 text-sm text-text-primary">
                  <p>
                    <span className="text-text-muted">Sender · </span>
                    {targetMessage.senderName}
                  </p>
                  {sentOk && (
                    <p>
                      <span className="text-text-muted">Sent · </span>
                      {formatReadAt(sent!)}
                    </p>
                  )}
                  {targetMessage.editedAt && (
                    <p>
                      <span className="text-text-muted">Edited · </span>
                      {formatReadAt(new Date(targetMessage.editedAt))}
                    </p>
                  )}
                  {st && (targetMessage.sender === 'agent' || targetMessage.sender === 'ai') && (
                    <>
                      <p>
                        <span className="text-text-muted">Delivered (WhatsApp) · </span>
                        {st.delivered ? 'Yes' : 'Pending'}
                      </p>
                      <p>
                        <span className="text-text-muted">Read by customer · </span>
                        {st.read ? 'Yes' : '—'}
                      </p>
                    </>
                  )}
                  {st && targetMessage.sender === 'customer' && (
                    <p>
                      <span className="text-text-muted">Read by assigned agent · </span>
                      {st.read ? 'Yes' : '—'}
                    </p>
                  )}
                </div>
              </div>
            </div>
          );
        }

        const readerName =
          targetMessage?.senderName === 'You'
            ? (agentFullName || getCurrentAgent()?.name || 'You')
            : targetMessage?.senderName === 'Admin'
              ? 'Admin'
              : (targetMessage?.senderName || title?.split(' ')[0] || 'Customer');
        const readByList = [{ name: readerName, readAt: new Date() }];
        return (
          <div
            className="fixed inset-0 z-30 flex items-start justify-center pt-20 bg-black/20"
            onClick={() => setMessageInfoId(null)}
          >
            <div
              className="bg-white rounded-xl shadow-2xl w-full max-w-sm overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <span className="font-semibold text-text-primary flex items-center gap-1.5">
                  <span className="text-primary">✔✔</span> READ BY
                </span>
                <button
                  type="button"
                  onClick={() => setMessageInfoId(null)}
                  className="p-1.5 rounded-full hover:bg-panel text-text-muted"
                  aria-label="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="max-h-80 overflow-y-auto">
                {readByList.map((reader, idx) => {
                  const isYou = reader.name === 'You' || reader.name === agentFullName;
                  return (
                    <div
                      key={reader.name}
                      className={`flex items-center gap-3 px-4 py-3 ${idx > 0 ? 'border-t border-border' : ''}`}
                    >
                      <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold flex-shrink-0 overflow-hidden">
                        {isYou && agentAvatarUrl ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={agentAvatarUrl} alt="" className="w-full h-full object-cover" />
                        ) : (
                          reader.name.charAt(0)
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-text-primary truncate">{reader.name}</p>
                        <p className="text-xs text-text-muted">{formatReadAt(reader.readAt)}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })()}

      {/* Group Info Modal */}
      {isTeamChannel && showGroupInfo && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
          <div className="bg-white w-full max-w-4xl h-[520px] rounded-xl shadow-2xl flex overflow-hidden">
            {/* Left navigation */}
            <div className="w-56 border-r border-border bg-panel">
              <div className="px-4 py-4 border-b border-border">
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                  Group
                </p>
              </div>
              <nav className="py-2">
                <button
                  type="button"
                  className={`w-full flex items-center gap-2 px-4 py-2 text-sm text-left ${
                    activeGroupTab === 'info'
                      ? 'bg-white text-text-primary'
                      : 'text-text-secondary hover:bg-white/60'
                  }`}
                  onClick={() => setActiveGroupTab('info')}
                >
                  <Info className="w-4 h-4" />
                  Info
                </button>
                <button
                  type="button"
                  className={`w-full flex items-center gap-2 px-4 py-2 text-sm text-left ${
                    activeGroupTab === 'media'
                      ? 'bg-white text-text-primary'
                      : 'text-text-secondary hover:bg-white/60'
                  }`}
                  onClick={() => setActiveGroupTab('media')}
                >
                  <ImageIcon className="w-4 h-4" />
                  Media, links and docs
                </button>
                <button
                  type="button"
                  className={`w-full flex items-center gap-2 px-4 py-2 text-sm text-left ${
                    activeGroupTab === 'starred'
                      ? 'bg-white text-text-primary'
                      : 'text-text-secondary hover:bg-white/60'
                  }`}
                  onClick={() => setActiveGroupTab('starred')}
                >
                  <Star className="w-4 h-4" />
                  Starred
                </button>
                <button
                  type="button"
                  className={`w-full flex items-center gap-2 px-4 py-2 text-sm text-left ${
                    activeGroupTab === 'members'
                      ? 'bg-white text-text-primary'
                      : 'text-text-secondary hover:bg-white/60'
                  }`}
                  onClick={() => setActiveGroupTab('members')}
                >
                  <Users className="w-4 h-4" />
                  Members
                </button>
              </nav>
            </div>

            {/* Right content */}
            <div className="flex-1 flex flex-col">
              <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                <h2 className="font-semibold text-text-primary">
                  {teamName ? `${teamName} - Internal` : 'Team Channel'}
                </h2>
                <button
                  type="button"
                  onClick={() => setShowGroupInfo(false)}
                  className="p-1.5 rounded-full hover:bg-panel text-text-secondary"
                  aria-label="Close group info"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6">
                {activeGroupTab === 'info' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-4">
                      <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold text-xl">
                        {(teamName || 'Team')[0]}
                      </div>
                      <div>
                        <p className="font-semibold text-text-primary">
                          {teamName ? `${teamName} - Internal` : 'Team Channel'}
                        </p>
                        <p className="text-sm text-text-secondary">
                          Group · {teamMemberNames.length} members
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {activeGroupTab === 'members' && (
                  <div className="space-y-3">
                    {teamMemberNames.map((name) => {
                      const isYou = name === 'You' || name === agentFullName;
                      return (
                        <div
                          key={name}
                          className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-panel"
                        >
                          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold overflow-hidden flex-shrink-0">
                            {isYou && agentAvatarUrl ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={agentAvatarUrl} alt="" className="w-full h-full object-cover" />
                            ) : (
                              name[0]
                            )}
                          </div>
                          <span className="text-sm text-text-primary">{name}</span>
                        </div>
                      );
                    })}
                  </div>
                )}

                {activeGroupTab === 'media' && (
                  <div className="space-y-6">
                    {assetError && <p className="text-xs text-status-error">{assetError}</p>}
                    <div>
                      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                        Media
                      </h3>
                      <div className="grid grid-cols-4 gap-2">
                        {teamAssetsLoading ? (
                          <p className="text-xs text-text-muted">Loading media...</p>
                        ) : teamAssets.filter((a) => a.asset_type === 'image').length === 0 && sharedChatMedia.length === 0 ? (
                          <p className="text-xs text-text-muted col-span-4">No data exists.</p>
                        ) : (
                          <>
                            {sharedChatMedia.map((m) => (
                              m.isHeic ? (
                                <a
                                  key={m.id}
                                  href={m.url}
                                  download={m.name}
                                  className="aspect-square rounded-lg bg-panel border border-border flex items-center justify-center p-2 text-center"
                                  title={m.name}
                                >
                                  <span className="text-[10px] text-text-muted break-all">{m.name}</span>
                                </a>
                              ) : (
                                <button
                                  type="button"
                                  key={m.id}
                                  onClick={() => setPreviewImageSrc(m.url)}
                                  className="aspect-square rounded-lg bg-panel border border-border overflow-hidden"
                                  title={m.name}
                                >
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img src={m.url} alt={m.name} className="w-full h-full object-cover" />
                                </button>
                              )
                            ))}
                            {teamAssets
                              .filter((a) => a.asset_type === 'image')
                              .map((a) => (
                                <button
                                  type="button"
                                  key={a.id}
                                  onClick={() => setPreviewImageSrc(a.content_base64 ? `data:${a.mime_type || 'image/*'};base64,${a.content_base64}` : null)}
                                  className="aspect-square rounded-lg bg-panel border border-border overflow-hidden"
                                  title={a.file_name || a.title || 'Image'}
                                >
                                  {a.content_base64 ? (
                                    // eslint-disable-next-line @next/next/no-img-element
                                    <img
                                      src={`data:${a.mime_type || 'image/*'};base64,${a.content_base64}`}
                                      alt={a.file_name || a.title || 'Image'}
                                      className="w-full h-full object-cover"
                                    />
                                  ) : (
                                    <span className="text-[10px] text-text-muted">Image</span>
                                  )}
                                </button>
                              ))}
                          </>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                      <div>
                        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                          Links
                        </h3>
                        <ul className="space-y-2 text-sm">
                          {teamAssets.filter((a) => a.asset_type === 'link').length === 0 ? (
                            <li className="text-xs text-text-muted">No data exists.</li>
                          ) : (
                            teamAssets.filter((a) => a.asset_type === 'link').map((a) => (
                              <li key={a.id}>
                                <a
                                  href={a.url || '#'}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="flex items-center gap-2 text-primary hover:underline"
                                >
                                  <Link2 className="w-4 h-4" />
                                  {a.title || a.url}
                                </a>
                              </li>
                            ))
                          )}
                        </ul>
                      </div>
                      <div>
                        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                          Docs
                        </h3>
                        <ul className="space-y-2 text-sm">
                          {teamAssets.filter((a) => a.asset_type === 'doc').length === 0 && sharedChatDocs.length === 0 ? (
                            <li className="text-xs text-text-muted">No data exists.</li>
                          ) : (
                            <>
                              {sharedChatDocs.map((d) => (
                                <li key={d.id}>
                                  <a
                                    href={d.url}
                                    download={d.name}
                                    className="flex items-center gap-2 text-text-primary hover:underline"
                                  >
                                    <FileText className="w-4 h-4 text-text-muted" />
                                    {d.name}
                                  </a>
                                </li>
                              ))}
                              {teamAssets.filter((a) => a.asset_type === 'doc').map((a) => (
                                <li key={a.id}>
                                  <a
                                    href={a.content_base64 ? `data:${a.mime_type || 'application/octet-stream'};base64,${a.content_base64}` : '#'}
                                    download={a.file_name || a.title || 'document'}
                                    className="flex items-center gap-2 text-text-primary hover:underline"
                                  >
                                    <FileText className="w-4 h-4 text-text-muted" />
                                    {a.file_name || a.title || 'Document'}
                                  </a>
                                </li>
                              ))}
                            </>
                          )}
                        </ul>
                      </div>
                    </div>
                  </div>
                )}

                {activeGroupTab === 'starred' && (
                  <div className="space-y-3">
                    {messages.filter(
                      (m) => starredIds.includes(m.id) && !deletedForMeIds.includes(m.id),
                    ).length === 0 ? (
                      <p className="text-sm text-text-muted">
                        No starred messages. Use the star icon next to a message to save it here.
                      </p>
                    ) : (
                      messages
                        .filter(
                          (m) =>
                            starredIds.includes(m.id) && !deletedForMeIds.includes(m.id),
                        )
                        .map((m) => (
                          <button
                            key={m.id}
                            type="button"
                            onClick={() => scrollToMessage(m.id)}
                            className="w-full text-left px-3 py-2 rounded-lg hover:bg-panel text-sm"
                          >
                            <p className="text-xs text-text-muted mb-0.5">
                              {m.senderName} • {m.timestamp}
                            </p>
                            <p className="text-text-primary line-clamp-2">{m.content}</p>
                          </button>
                        ))
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Agent Profile Modal */}
      {isDmPage && showAgentProfile && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/40"
          onClick={() => setShowAgentProfile(false)}
        >
          <div
            className="relative bg-white rounded-2xl shadow-2xl p-8 max-w-sm w-full mx-4 flex flex-col items-center"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setShowAgentProfile(false)}
              className="absolute top-4 right-4 p-1.5 rounded-full hover:bg-panel text-text-secondary"
              aria-label="Close profile"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="w-40 h-40 rounded-full bg-primary/10 flex items-center justify-center text-primary text-5xl font-semibold flex-shrink-0 mb-4">
              {title ? title.charAt(0) : '?'}
            </div>
            <h2 className="text-xl font-semibold text-text-primary text-center">
              {title || 'Agent'}
            </h2>
            <p className="text-sm text-text-muted mt-1">Direct message</p>
          </div>
        </div>
      )}

      {previewImageSrc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-6"
          onClick={() => setPreviewImageSrc(null)}
        >
          <div className="relative max-w-5xl max-h-[85vh] w-full flex items-center justify-center">
            <button
              type="button"
              onClick={() => setPreviewImageSrc(null)}
              className="absolute right-2 top-2 p-2 rounded-full bg-black/50 text-white hover:bg-black/70"
              aria-label="Close image preview"
            >
              <X className="w-5 h-5" />
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={previewImageSrc} alt="Preview" className="max-w-full max-h-[85vh] rounded-lg shadow-2xl" />
          </div>
        </div>
      )}
    </div>
  );
}