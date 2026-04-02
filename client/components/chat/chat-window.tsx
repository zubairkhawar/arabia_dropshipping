'use client';

import { useState, useEffect, useRef } from 'react';
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
  Copy,
  Trash2,
  ChevronDown,
  Plus,
  Mic,
  Square,
  Play,
  Pause,
  UserPlus,
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
  timestamp: string;
  /** ISO date string for actual time and date grouping */
  sentAt?: string;
  reactions?: MessageReaction[];
  replyTo?: { id: number; senderName: string; content: string };
  attachment?: MessageAttachment;
}

interface TeamChannelMessageRow {
  id: number;
  team_id: number;
  sender_agent_id: number;
  sender_name: string;
  content: string;
  created_at: string;
}

interface TeamChannelPayload {
  text?: string;
  attachment?: MessageAttachment;
}

const isHeicLikeAttachment = (attachment?: MessageAttachment) => {
  if (!attachment) return false;
  const n = attachment.name.toLowerCase();
  return n.endsWith('.heic') || n.endsWith('.heif');
};

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
  const { getMessagesBySlug, loadMessagesBySlug, sendMessageBySlug } = useDmChats();
  const API_BASE =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    'https://arabia-dropshipping.onrender.com';
  const TENANT_ID = 1;
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
    setMessages(stored as Message[]);
  }, [isInboxWithSelection, inboxConv?.selectedId]);

  useEffect(() => {
    if (!isInternalChat || !isDmPage || !dmSlug) return;
    void loadMessagesBySlug(dmSlug);
  }, [isInternalChat, isDmPage, dmSlug, loadMessagesBySlug]);

  useEffect(() => {
    if (!isInternalChat || !isDmPage || !dmSlug) return;
    const rows = getMessagesBySlug(dmSlug);
    const mapped: Message[] = rows.map((m) => ({
      id: m.id,
      content: m.content,
      sender: 'agent',
      senderName: m.senderName,
      timestamp: new Date(m.createdAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
      sentAt: m.createdAt,
    }));
    setMessages(mapped);
  }, [isInternalChat, isDmPage, dmSlug, getMessagesBySlug]);

  useEffect(() => {
    if (!isInternalChat || !isTeamChannel || !teamId) return;
    const currentAgentId = Number(getCurrentAgent()?.id || 0);
    const loadTeamMessages = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/teams/${Number(teamId)}/channel/messages?tenant_id=${TENANT_ID}`);
        if (!res.ok) throw new Error('Failed to load team messages');
        const rows = (await res.json()) as TeamChannelMessageRow[];
        const mapped: Message[] = (Array.isArray(rows) ? rows : []).map((m) => {
          const payload = decodeTeamMessageContent(m.content);
          return {
            id: m.id,
            content: payload.text || '',
            sender: 'agent',
            senderName: m.sender_agent_id === currentAgentId ? 'You' : m.sender_name,
            senderAgentId: m.sender_agent_id,
            timestamp: new Date(m.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
            sentAt: m.created_at,
            attachment: payload.attachment,
          };
        });
        setMessages(mapped);
      } catch {
        setMessages([]);
      }
    };
    void loadTeamMessages();
  }, [isInternalChat, isTeamChannel, teamId, getCurrentAgent, API_BASE, TENANT_ID]);
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
  const [dropdownPlaceAbove, setDropdownPlaceAbove] = useState(true);
  const [showAttachmentMenu, setShowAttachmentMenu] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
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

  const DROPDOWN_APPROX_HEIGHT = 320;
  const mentionCandidates = teamMemberNames
    ? teamMemberNames.filter((n) => n.toLowerCase().includes((mentionFilter || '').toLowerCase()))
    : [];

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

  const getMessageStyle = (message: Message, outgoing: boolean) => {
    if (outgoing) return 'bg-chat-user text-white';
    if (message.senderName === 'Admin') return 'bg-primary/15 text-primary border border-primary/30';
    if (message.sender === 'agent') return 'bg-chat-agent text-text-primary';
    return 'bg-chat-ai text-text-primary';
  };

  const isOutgoingMessage = (message: Message) => {
    if (isInternalChat && isTeamChannel) {
      if (broadcastMode && message.senderName === 'Admin') return true;
      if (viewerAgentId && message.senderAgentId) return message.senderAgentId === viewerAgentId;
      return message.senderName === 'You';
    }
    if (isInternalChat) return message.senderName === 'You';
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
    const currentUserId = 'me';
    const currentUserName = 'You';
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== id) return m;
        const list = m.reactions ?? [];
        const withoutMe = list.filter((r) => r.userId !== currentUserId);
        const existing = list.find((r) => r.userId === currentUserId);
        if (existing?.emoji === emoji) {
          return { ...m, reactions: withoutMe.length > 0 ? withoutMe : undefined };
        }
        return {
          ...m,
          reactions: [
            ...withoutMe,
            { emoji, userId: currentUserId, userName: currentUserName, reactedAt: new Date().toISOString() },
          ],
        };
      }),
    );
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

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    handleScrollStickyDate();
    el.addEventListener('scroll', handleScrollStickyDate);
    return () => el.removeEventListener('scroll', handleScrollStickyDate);
  }, [filteredMessages.length, teamEvents.length]);

  const deleteMessage = (id: number) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
    setStarredIds((prev) => prev.filter((mId) => mId !== id));
    setDeletedForMeIds((prev) => prev.filter((mId) => mId !== id));
    setActiveMessageMenuId(null);
  };

  const deleteForMe = (id: number) => {
    setDeletedForMeIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setStarredIds((prev) => prev.filter((mId) => mId !== id));
    setActiveMessageMenuId(null);
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
      void sendMessageBySlug(dmSlug, newMsg.content);
      setInputValue('');
      setReplyingTo(null);
      setPendingAttachment(null);
      setShowMentionDropdown(false);
      return;
    }
    if (isInternalChat && isTeamChannel && teamId) {
      try {
        const senderId = Number(getCurrentAgent()?.id || 0);
        if (!senderId) throw new Error('Agent not found');
        const res = await fetch(`${API_BASE}/api/teams/${Number(teamId)}/channel/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tenant_id: TENANT_ID,
            sender_agent_id: senderId,
            content: encodeTeamMessageContent({
              text: text || '',
              attachment: pendingAttachment ?? undefined,
            }),
          }),
        });
        if (!res.ok) throw new Error('Failed to send team message');
        const saved = (await res.json()) as TeamChannelMessageRow;
        setMessages((prev) => [
          ...prev,
          {
            id: saved.id,
            content: text || (pendingAttachment?.name || ''),
            sender: 'agent',
            senderName: 'You',
            senderAgentId: senderId,
            timestamp: new Date(saved.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
            sentAt: saved.created_at,
            attachment: pendingAttachment ?? undefined,
          },
        ]);
      } catch {
        addSystemNote('Message failed to send. Please try again.');
      } finally {
        setInputValue('');
        setReplyingTo(null);
        setPendingAttachment(null);
        setShowMentionDropdown(false);
      }
      return;
    }
    setMessages((prev) => [...prev, newMsg]);
    setInputValue('');
    setReplyingTo(null);
    setPendingAttachment(null);
    setShowMentionDropdown(false);
    if (inboxConv?.selectedId != null) {
      inboxConv.appendMessage(inboxConv.selectedId, newMsg as InboxMessage);
      inboxConv.markAgentReplied(inboxConv.selectedId);
    }
  };

  const startVoiceRecording = () => {
    if (typeof window === 'undefined' || !navigator.mediaDevices?.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      const recorder = new MediaRecorder(stream);
      recordingChunksRef.current = [];
      recordingStartRef.current = Date.now();
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordingChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(recordingChunksRef.current, { type: 'audio/webm' });
        const url = URL.createObjectURL(blob);
        const durationSeconds = Math.round((Date.now() - recordingStartRef.current) / 1000);
        setPendingAttachment({
          type: 'voice',
          name: 'Voice message',
          url,
          durationSeconds: durationSeconds || 1,
        });
        setShowAttachmentMenu(false);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    });
  };

  const stopVoiceRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
    setIsRecording(false);
  };

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
    if (!showBroadcastInput || !teamMemberNames?.length) return;
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

  const insertMention = (name: string) => {
    const start = mentionAnchorRef.current;
    const cursor = inputRef.current?.selectionStart ?? inputValue.length;
    const newValue =
      inputValue.slice(0, start) + `@${name} ` + inputValue.slice(cursor);
    setInputValue(newValue);
    setShowMentionDropdown(false);
    setTimeout(() => {
      inputRef.current?.focus();
      const pos = start + name.length + 2;
      inputRef.current?.setSelectionRange(pos, pos);
    }, 0);
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showMentionDropdown && mentionCandidates.length > 0) {
      if (e.key === 'Escape') {
        setShowMentionDropdown(false);
        e.preventDefault();
        return;
      }
      if (e.key === 'ArrowDown') {
        setMentionIndex((i) => (i + 1) % mentionCandidates.length);
        e.preventDefault();
        return;
      }
      if (e.key === 'ArrowUp') {
        setMentionIndex((i) => (i - 1 + mentionCandidates.length) % mentionCandidates.length);
        e.preventDefault();
        return;
      }
      if (e.key === 'Enter' && mentionCandidates.length > 0) {
        insertMention(mentionCandidates[mentionIndex]);
        e.preventDefault();
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

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
        className="flex-1 overflow-y-auto p-6 space-y-4 bg-panel relative"
      >
        {selectedConv?.reopenedAt && selectedConv.closedAt && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            You closed this conversation on {selectedConv.closedAt}. The customer has messaged again.
          </div>
        )}
        {stickyDate && (
          <div className="sticky top-0 z-10 flex justify-center py-2 pointer-events-none">
            <span className="bg-white/95 border border-border rounded-full px-3 py-1.5 text-xs font-medium text-text-secondary shadow-sm">
              {formatDateLabel(stickyDate + 'T12:00:00')}
            </span>
          </div>
        )}
        {unifiedGroups.map((group) => (
          <div key={group.dateKey} className="space-y-4">
            <div
              data-date-key={group.dateKey}
              className="flex justify-center py-2"
            >
              <span className="bg-white border border-border rounded-full px-3 py-1.5 text-xs font-medium text-text-muted shadow-sm">
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
            {group.messages.map((message) => {
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
              const isStarred = starredIds.includes(message.id);
              const showMenu = activeMessageMenuId === message.id;
              const showReactions = activeReactionPickerId === message.id;
              const reactionEmojis = ['👍', '❤️', '😂', '😮', '😢', '🙏', '👏', '😁'];
              const reactionList = message.reactions ?? [];
              const myReaction = reactionList.find((r) => r.userId === 'me')?.emoji;
              const aggregated = Object.entries(
                reactionList.reduce<Record<string, number>>((acc, r) => {
                  acc[r.emoji] = (acc[r.emoji] ?? 0) + 1;
                  return acc;
                }, {}),
              ).map(([emoji, count]) => ({ emoji, count }));
              const showReactionDetail = reactionDetailMessageId === message.id;
              const emojiOnly = !message.attachment && isEmojiOnly(message.content);

              return (
                <div
                  key={message.id}
                  id={`message-${message.id}`}
                  className={`flex w-full items-start gap-2 ${outgoing ? 'justify-end' : 'justify-start'}`}
                >
                  {isTeamChannel && !outgoing && (
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold flex-shrink-0 overflow-hidden">
                      {message.senderName === 'You' && agentAvatarUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={agentAvatarUrl} alt="" className="w-full h-full object-cover" />
                      ) : (
                        message.senderName.charAt(0)
                      )}
                    </div>
                  )}
                  <div className={`relative group max-w-[85%] ${outgoing ? 'flex flex-col items-end' : ''}`}>
                    <div
                      className={`relative max-w-message-bubble min-w-[8rem] rounded-lg px-3 py-3.5 pl-3 pr-10 ${getMessageStyle(message, outgoing)}`}
                    >
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() =>
                            setActiveMessageMenuId((current) =>
                              current === message.id ? null : message.id,
                            )
                          }
                          className="absolute top-2 right-2 w-7 h-7 flex items-center justify-center rounded-full bg-white/30 hover:bg-white/50 text-current opacity-80 hover:opacity-100 transition-opacity flex-shrink-0"
                          aria-label="Message options"
                        >
                          <ChevronDown className="w-4 h-4" />
                        </button>
                      )}

                      <div className="pr-1 min-w-0 space-y-1">
                        {message.replyTo && (
                          <div
                            className={`mb-2 pl-2 border-l-4 rounded border-primary ${
                              outgoing ? 'bg-white/20' : 'bg-black/5'
                            }`}
                          >
                            <p className={`text-xs font-semibold ${outgoing ? 'text-white' : 'text-primary'}`}>
                              {message.replyTo.senderName}
                            </p>
                            <p
                              className={`text-xs truncate max-w-full ${
                                outgoing ? 'text-white/90' : 'text-text-secondary'
                              }`}
                              title={message.replyTo.content}
                            >
                              {message.replyTo.content}
                            </p>
                          </div>
                        )}
                        {!outgoing && (
                          <p className="text-xs font-medium mb-1 opacity-75">{message.senderName}</p>
                        )}
                        {message.attachment && (
                          <div className={`mb-2 rounded-lg overflow-hidden ${outgoing ? 'bg-white/20' : 'bg-black/5'}`}>
                            {message.attachment.type === 'photo' && (
                              isHeicLikeAttachment(message.attachment) ? (
                                <a
                                  href={message.attachment.url}
                                  download={message.attachment.name}
                                  className={`flex items-center gap-2 px-2 py-2 rounded-lg ${outgoing ? 'text-white hover:bg-white/10' : 'text-text-primary hover:bg-black/5'}`}
                                >
                                  <ImageIcon className="w-5 h-5 flex-shrink-0" />
                                  <span className="text-sm truncate">{message.attachment.name}</span>
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
                                  className="max-w-full max-h-48 object-cover rounded-lg"
                                />
                              </button>
                              )
                            )}
                            {message.attachment.type === 'file' && (
                              <a
                                href={message.attachment.url}
                                download={message.attachment.name}
                                className={`flex items-center gap-2 px-2 py-2 rounded-lg ${outgoing ? 'text-white hover:bg-white/10' : 'text-text-primary hover:bg-black/5'}`}
                              >
                                <FileText className="w-5 h-5 flex-shrink-0" />
                                <span className="text-sm truncate">{message.attachment.name}</span>
                              </a>
                            )}
                            {message.attachment.type === 'voice' && (
                              <div className={`flex items-center gap-2 py-1 ${outgoing ? 'text-white' : 'text-text-primary'}`}>
                                <div className="flex items-center gap-2 min-w-0 flex-1">
                                  <div className="relative flex-shrink-0">
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${outgoing ? 'bg-white/20' : 'bg-black/10'}`}>
                                      <Mic className={`w-4 h-4 ${outgoing ? 'text-blue-200' : 'text-status-info'}`} />
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
                                    className={`p-1 rounded-full flex-shrink-0 ${outgoing ? 'text-white/90 hover:bg-white/20' : 'text-text-primary hover:bg-black/10'}`}
                                    aria-label={playingVoiceId === message.id ? 'Pause' : 'Play voice message'}
                                  >
                                    {playingVoiceId === message.id ? (
                                      <Pause className="w-5 h-5" fill="currentColor" />
                                    ) : (
                                      <Play className="w-5 h-5" fill="currentColor" />
                                    )}
                                  </button>
                                  <div className="flex-1 min-w-0 flex items-center gap-1.5">
                                    <div className="flex-1 h-1.5 rounded-full overflow-hidden bg-black/15 min-w-[4rem]">
                                      <div
                                        className={`h-full rounded-full transition-all duration-150 ${outgoing ? 'bg-blue-200' : 'bg-status-info/70'}`}
                                        style={{ width: `${((voiceProgress[message.id] ?? 0) * 100).toFixed(1)}%` }}
                                      />
                                    </div>
                                    <div className="flex gap-0.5 flex-shrink-0">
                                      {VOICE_WAVEFORM_BARS.map((h, i) => (
                                        <div
                                          key={i}
                                          className={`w-0.5 rounded-full ${outgoing ? 'bg-white/50' : 'bg-text-muted'}`}
                                          style={{ height: `${(h / 100) * 12}px`, minHeight: 4 }}
                                        />
                                      ))}
                                    </div>
                                  </div>
                                </div>
                                <span className={`text-xs flex-shrink-0 ${outgoing ? 'text-white/80' : 'text-text-muted'}`}>
                                  {formatVoiceDuration(message.attachment.durationSeconds ?? 0)}
                                </span>
                              </div>
                            )}
                          </div>
                        )}
                        <p className={`leading-relaxed break-words whitespace-pre-wrap ${emojiOnly ? 'text-5xl' : 'text-sm'} ${outgoing ? 'text-white' : 'text-text-primary'}`}>
                          {message.content}
                        </p>
                        <div className="mt-2 flex items-center justify-between gap-2">
                          <span
                            className={`text-xs ${
                              outgoing ? 'text-white/75' : 'text-text-muted'
                            }`}
                          >
                            {formatMessageTime(message.sentAt, message.timestamp)}
                          </span>
                          <span className="flex items-center gap-1">
                            {isTeamChannel && isStarred && (
                              <Star className={`w-3 h-3 flex-shrink-0 ${outgoing ? 'text-white' : 'text-primary'}`} />
                            )}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Reaction summary and react button: below bubble */}
                    <div
                      className={`mt-1 flex gap-1 items-center ${
                        outgoing ? 'justify-end' : 'justify-start'
                      }`}
                    >
                      {aggregated.length > 0 && (
                        <button
                          type="button"
                          onClick={() =>
                            setReactionDetailMessageId((id) =>
                              id === message.id ? null : message.id,
                            )
                          }
                          className="inline-flex items-center gap-1 rounded-full border border-border bg-white shadow-sm px-2 py-1 text-sm hover:bg-panel"
                        >
                          {aggregated.map(({ emoji, count }) => (
                            <span key={emoji} className="inline-flex items-center gap-0.5">
                              {emoji}
                              {count > 1 && (
                                <span className="text-xs text-text-muted">{count}</span>
                              )}
                            </span>
                          ))}
                        </button>
                      )}
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() => setActiveReactionPickerId(message.id)}
                          className={`p-1 rounded-full border transition-colors flex-shrink-0 ${
                            myReaction
                              ? 'bg-primary/20 border-primary text-primary'
                              : 'bg-white/80 border-border shadow-sm text-text-muted hover:text-primary hover:border-primary'
                          }`}
                          aria-label="React"
                        >
                          {myReaction ? (
                            <span className="text-base">{myReaction}</span>
                          ) : (
                            <Smile className="w-4 h-4" />
                          )}
                        </button>
                      )}
                    </div>

                    {/* Who reacted detail popover */}
                    {showReactionDetail && reactionList.length > 0 && (
                      <>
                        <div className="fixed inset-0 z-10" onClick={() => setReactionDetailMessageId(null)} aria-hidden />
                        <div
                          className={`absolute z-20 w-64 bg-white border border-border rounded-xl shadow-xl overflow-hidden ${
                            outgoing ? 'right-0' : 'left-0'
                          } bottom-full mb-1`}
                        >
                          <div className="px-3 py-2 border-b border-border flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-text-primary">All {reactionList.length}</span>
                            {aggregated.map(({ emoji, count }) => (
                              <span key={emoji} className="text-sm text-text-muted">
                                {emoji} {count}
                              </span>
                            ))}
                          </div>
                          <div className="max-h-48 overflow-y-auto">
                            {reactionList.map((r, i) => (
                              <div
                                key={`${r.userId}-${r.emoji}-${i}`}
                                className="flex items-center gap-3 px-3 py-2 hover:bg-panel border-b border-border last:border-b-0"
                              >
                                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold flex-shrink-0 overflow-hidden">
                                  {r.userName === 'You' && agentAvatarUrl ? (
                                    // eslint-disable-next-line @next/next/no-img-element
                                    <img src={agentAvatarUrl} alt="" className="w-full h-full object-cover" />
                                  ) : (
                                    r.userName.charAt(0)
                                  )}
                                </div>
                                <div className="min-w-0 flex-1">
                                  <p className="text-sm font-medium text-text-primary truncate">{r.userName}</p>
                                  <p className="text-xs text-text-muted">{formatReactionTime(r.reactedAt)}</p>
                                </div>
                                <span className="text-lg flex-shrink-0">{r.emoji}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </>
                    )}

                    {!readOnly && showMenu && (
                      <div
                        className={`absolute w-48 bg-white border border-border rounded-lg shadow-xl z-20 py-1 text-sm ${
                          outgoing
                            ? dropdownPlaceAbove
                              ? 'right-0 bottom-full mb-1'
                              : 'right-full mr-2 top-0'
                            : dropdownPlaceAbove
                              ? 'left-0 bottom-full mb-1'
                              : 'left-0 top-full mt-1'
                        }`}
                      >
                        <button
                          type="button"
                          className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-panel text-left"
                          onClick={() => {
                            setReplyingTo({
                              id: message.id,
                              senderName: message.senderName,
                              content: message.content,
                            });
                            setActiveMessageMenuId(null);
                          }}
                        >
                          <CornerDownLeft className="w-4 h-4 text-text-muted" />
                          Reply
                        </button>
                        {outgoing && (
                          <button
                            type="button"
                            className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-panel text-left"
                            onClick={() => setActiveReactionPickerId(message.id)}
                          >
                            <Smile className="w-4 h-4 text-text-muted" />
                            React
                          </button>
                        )}
                        <button
                          type="button"
                          className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-panel text-left"
                          onClick={() => toggleStar(message.id)}
                        >
                          <Star
                            className={`w-4 h-4 ${
                              isStarred ? 'text-primary fill-primary' : 'text-text-muted'
                            }`}
                          />
                          {isStarred ? 'Unstar' : 'Star'}
                        </button>
                        <button
                          type="button"
                          className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-panel text-left"
                          onClick={() => {
                            if (navigator.clipboard?.writeText) {
                              navigator.clipboard.writeText(message.content).catch(() => undefined);
                            }
                            setActiveMessageMenuId(null);
                          }}
                        >
                          <Copy className="w-4 h-4 text-text-muted" />
                          Copy
                        </button>
                        {outgoing && (
                          <button
                            type="button"
                            className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-panel text-left"
                            onClick={() => {
                              setMessageInfoId(message.id);
                              setActiveMessageMenuId(null);
                            }}
                          >
                            <Info className="w-4 h-4 text-text-muted" />
                            Info
                          </button>
                        )}
                        <div className="border-t border-border my-1" />
                        {outgoing ? (
                          <>
                            <button
                              type="button"
                              className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-panel text-left text-status-error"
                              onClick={() => deleteForMe(message.id)}
                            >
                              <Trash2 className="w-4 h-4" />
                              Delete for me
                            </button>
                            <button
                              type="button"
                              className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-panel text-left text-status-error"
                              onClick={() => deleteMessage(message.id)}
                            >
                              <Trash2 className="w-4 h-4" />
                              Delete for everyone
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-panel text-left text-status-error"
                            onClick={() => deleteForMe(message.id)}
                          >
                            <Trash2 className="w-4 h-4" />
                            Delete for me
                          </button>
                        )}
                      </div>
                    )}

                    {!readOnly && showReactions && (
                      <div
                        className={`absolute ${
                          outgoing ? 'right-0' : 'left-0'
                        } mt-2 w-64 bg-white border border-border rounded-xl shadow-2xl z-30 p-3`}
                      >
                        <p className="text-xs text-text-muted mb-2">React (one at a time, click again to remove)</p>
                        <div className="flex flex-wrap gap-1.5 mb-2">
                          {reactionEmojis.map((emoji) => {
                            const isSelected = myReaction === emoji;
                            return (
                              <button
                                key={emoji}
                                type="button"
                                className={`w-7 h-7 rounded-full flex items-center justify-center text-lg transition-colors ${
                                  isSelected
                                    ? 'bg-primary/20 border-2 border-primary'
                                    : 'hover:bg-panel'
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
                  {isTeamChannel && outgoing && (
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold flex-shrink-0 overflow-hidden">
                      {agentAvatarUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={agentAvatarUrl} alt="" className="w-full h-full object-cover" />
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
                  showBroadcastInput
                    ? 'Type a message... Use @ to tag an agent'
                    : replyingTo
                      ? `Reply to ${replyingTo.senderName}...`
                      : 'Type a message...'
                }
                className="flex-1 min-w-0 px-4 py-2.5 focus:outline-none text-sm bg-transparent"
                onKeyDown={handleInputKeyDown}
              />
              
              {showBroadcastInput && showMentionDropdown && mentionCandidates.length > 0 && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowMentionDropdown(false)}
                    aria-hidden
                  />
                  <div className="absolute left-0 right-0 bottom-full mb-1 max-h-48 overflow-y-auto bg-white border border-border rounded-lg shadow-xl z-20 py-1">
                    {mentionCandidates.map((name, i) => (
                      <button
                        key={name}
                        type="button"
                        className={`w-full px-3 py-2 text-left text-sm hover:bg-panel text-text-primary flex items-center gap-2 ${i === mentionIndex ? 'bg-panel' : ''}`}
                        onClick={() => insertMention(name)}
                      >
                        <User className="w-4 h-4 text-text-muted flex-shrink-0" />
                        {name}
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
            
            {!showBroadcastInput && (isRecording ? (
              <button
                type="button"
                onClick={stopVoiceRecording}
                className="p-2.5 rounded-full bg-status-error text-white hover:bg-status-error/90 flex-shrink-0"
                aria-label="Stop recording"
              >
                <Square className="w-5 h-5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => { setShowAttachmentMenu(false); setShowEmojiPicker(false); startVoiceRecording(); }}
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

      {/* Message Info Modal */}
      {messageInfoId !== null && (() => {
        const targetMessage = messages.find((m) => m.id === messageInfoId) ?? null;
        const readerName =
          targetMessage?.senderName === 'You'
            ? (agentFullName || getCurrentAgent()?.name || 'You')
            : (targetMessage?.senderName || title?.split(' ')[0] || 'Customer');
        const readByList = [{ name: readerName, readAt: new Date() }];
        const formatReadAt = (d: Date) =>
          `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getFullYear()} ${d.getHours() % 12 || 12}:${d.getMinutes().toString().padStart(2, '0')} ${d.getHours() >= 12 ? 'PM' : 'AM'}`;
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