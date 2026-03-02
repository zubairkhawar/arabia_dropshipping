'use client';

import { useState, useEffect } from 'react';
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
} from 'lucide-react';

interface Message {
  id: number;
  content: string;
  sender: 'customer' | 'agent' | 'ai';
  senderName: string;
  timestamp: string;
  reactions?: string[];
  replyTo?: { id: number; senderName: string; content: string };
}

export interface ChatWindowProps {
  isInternalChat?: boolean;
  title?: string;
  subtitle?: string;
  showTransferControls?: boolean;
  /** For team channel: e.g. "Team A". Shown next to "# Team Channel" in header. */
  teamName?: string;
  /** For team channel: names shown in header subtitle, e.g. "Ali, Hamza, Sarah". */
  teamMemberNames?: string[];
}

const defaultCustomerMessages: Message[] = [
  {
    id: 1,
    content: 'Hello! How can I help you today?',
    sender: 'ai',
    senderName: 'AI Assistant',
    timestamp: '2 minutes ago',
  },
  {
    id: 2,
    content: 'I need help with my order #12345',
    sender: 'customer',
    senderName: 'Ahmed Ali',
    timestamp: '2 minutes ago',
  },
  {
    id: 3,
    content: 'I can help you with that. Let me check your order status.',
    sender: 'ai',
    senderName: 'AI Assistant',
    timestamp: '1 minute ago',
  },
  {
    id: 4,
    content:
      'Your order is currently in transit and will be delivered within 2-3 business days.',
    sender: 'ai',
    senderName: 'AI Assistant',
    timestamp: '1 minute ago',
  },
];

const defaultInternalMessages: Message[] = [
  {
    id: 1,
    content: 'Hey team, customer on order #12345 is asking about delivery ETA.',
    sender: 'agent',
    senderName: 'You',
    timestamp: 'Just now',
  },
  {
    id: 2,
    content: "I'll keep an eye on logistics updates for this one.",
    sender: 'agent',
    senderName: 'Hamza',
    timestamp: '1 min ago',
  },
  {
    id: 3,
    content: 'If it escalates, feel free to transfer to me.',
    sender: 'agent',
    senderName: 'Sarah',
    timestamp: '2 min ago',
  },
];

const internalTeamMembers = [
  { id: 'ali', name: 'Ali' },
  { id: 'sarah', name: 'Sarah' },
  { id: 'hamza', name: 'Hamza' },
];

const transferTargets = [
  { team: 'Team A', members: ['Ali'] },
  { team: 'Team B', members: ['Hamza'] },
  { team: 'Team C', members: ['Sarah'] },
];

export function ChatWindow({
  isInternalChat = false,
  title = 'Ahmed Ali',
  subtitle = 'Store: My Shopify Store • Order #12345',
  showTransferControls = false,
  teamName,
  teamMemberNames = [],
}: ChatWindowProps = {}) {
  const pathname = usePathname();
  const isTeamChannel = pathname?.startsWith('/agent/team');
  const isDmPage = pathname?.startsWith('/agent/dm');

  const [messages, setMessages] = useState<Message[]>(
    isInternalChat ? defaultInternalMessages : defaultCustomerMessages,
  );
  const [inputValue, setInputValue] = useState('');
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [showTransferMenu, setShowTransferMenu] = useState(false);
  const [showGroupInfo, setShowGroupInfo] = useState(false);
  const [activeGroupTab, setActiveGroupTab] = useState<'info' | 'media' | 'starred' | 'members'>('info');
  const [starredIds, setStarredIds] = useState<number[]>([]);
  const [activeMessageMenuId, setActiveMessageMenuId] = useState<number | null>(null);
  const [activeReactionPickerId, setActiveReactionPickerId] = useState<number | null>(null);
  const [deletedForMeIds, setDeletedForMeIds] = useState<number[]>([]);
  const [replyingTo, setReplyingTo] = useState<{ id: number; senderName: string; content: string } | null>(null);
  const [myReactions, setMyReactions] = useState<Record<number, string>>({});
  const [messageInfoId, setMessageInfoId] = useState<number | null>(null);
  const [dropdownPlaceAbove, setDropdownPlaceAbove] = useState(true);

  const DROPDOWN_APPROX_HEIGHT = 320;

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

  const getMessageStyle = (sender: string, senderName: string) => {
    if (sender === 'customer') return 'bg-chat-user text-white';
    if (senderName === 'You') return 'bg-chat-user text-white';
    if (sender === 'agent') return 'bg-chat-agent text-text-primary';
    return 'bg-chat-ai text-text-primary';
  };

  const isOutgoingMessage = (message: Message) =>
    message.sender === 'customer' || message.senderName === 'You';

  const addSystemNote = (content: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        content,
        sender: 'ai' as const,
        senderName: 'System',
        timestamp: 'Just now',
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
    setMyReactions((prev) => {
      const current = prev[id];
      if (current === emoji) {
        const next = { ...prev };
        delete next[id];
        return next;
      }
      return { ...prev, [id]: emoji };
    });
    setActiveReactionPickerId(null);
    setActiveMessageMenuId(null);
  };

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

  const sendMessage = () => {
    const text = inputValue.trim();
    if (!text) return;
    const nextId = Math.max(0, ...messages.map((m) => m.id)) + 1;
    setMessages((prev) => [
      ...prev,
      {
        id: nextId,
        content: text,
        sender: 'agent' as const,
        senderName: 'You',
        timestamp: 'Just now',
        replyTo: replyingTo ?? undefined,
      },
    ]);
    setInputValue('');
    setReplyingTo(null);
  };

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="h-chat-header border-b border-border px-6 flex items-center justify-between bg-white shrink-0">
        <div
          className={isTeamChannel ? 'cursor-pointer' : undefined}
          onClick={isTeamChannel ? () => setShowGroupInfo(true) : undefined}
        >
          {isInternalChat && !isTeamChannel && (
            <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-primary border border-primary rounded px-2 py-0.5 mb-1.5">
              Internal Chat
            </span>
          )}
          <h3 className="font-medium text-text-primary">
            {isTeamChannel && teamName ? `# Team Channel • ${teamName}` : title}
          </h3>
          <p className="text-xs text-text-secondary">
            {isTeamChannel && teamMemberNames.length > 0
              ? teamMemberNames.join(', ')
              : subtitle}
          </p>
        </div>
        <div className="relative flex items-center gap-2">
          {!isInternalChat && (
            <span className="text-xs px-2 py-1 bg-status-success text-white rounded">WhatsApp</span>
          )}
          {!isTeamChannel && (
            <>
          <button
            type="button"
            onClick={() => {
              setShowMoreMenu((v) => !v);
              setShowTransferMenu(false);
            }}
            className="text-text-secondary hover:text-text-primary p-1.5 rounded"
            aria-label="More options"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
          </button>

          {showMoreMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={closeMenus} aria-hidden />
              <div className="absolute right-0 top-full mt-2 w-56 bg-white border border-border rounded-lg shadow-xl z-20 py-1">
                <button
                  type="button"
                  onClick={() => setShowTransferMenu((v) => !v)}
                  className="w-full flex items-center justify-between px-4 py-2 text-sm hover:bg-panel text-text-primary"
                >
                  <span className="flex items-center gap-2">
                    <Users className="w-4 h-4" />
                    Transfer chat…
                  </span>
                  <ChevronRight className="w-4 h-4 text-text-muted" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    addSystemNote('Conversation sent back to AI bot.');
                    closeMenus();
                  }}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-panel text-text-primary"
                >
                  <Bot className="w-4 h-4" />
                  Send back to AI
                </button>
                <button
                  type="button"
                  onClick={() => {
                    addSystemNote('Conversation closed by agent.');
                    closeMenus();
                  }}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-panel text-status-error"
                >
                  <AlertCircle className="w-4 h-4" />
                  Close chat
                </button>
              </div>

              {showTransferMenu && (
                <div className="absolute right-full top-0 mr-1 w-56 bg-white border border-border rounded-lg shadow-xl z-30 py-1 max-h-64 overflow-y-auto">
                  {transferTargets.map((group) => (
                    <div key={group.team} className="px-4 py-2">
                      <div className="flex items-center gap-2 mb-1">
                        <Users className="w-4 h-4 text-text-muted" />
                        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                          {group.team}
                        </span>
                      </div>
                      <div className="space-y-1">
                        {group.members.map((name) => (
                          <button
                            key={name}
                            type="button"
                            onClick={() => {
                              addSystemNote(`Conversation transferred to ${name} (${group.team}).`);
                              closeMenus();
                            }}
                            className="w-full flex items-center gap-2 px-2 py-1 text-sm rounded hover:bg-panel text-text-primary"
                          >
                            <User className="w-4 h-4 text-text-muted" />
                            {name}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
            </>
          )}
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-panel">
        {messages
          .filter((m) => !deletedForMeIds.includes(m.id))
          .map((message) => {
          const outgoing = isOutgoingMessage(message);
          const isStarred = starredIds.includes(message.id);
          const showMenu = activeMessageMenuId === message.id;
          const showReactions = activeReactionPickerId === message.id;
          const reactionEmojis = ['👍', '❤️', '😂', '😮', '😢', '🙏', '👏', '😁'];

          const myReaction = myReactions[message.id];
          const displayReactions = myReaction ? [myReaction] : [];

          return (
            <div
              key={message.id}
              id={`message-${message.id}`}
              className={`flex w-full ${outgoing ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`relative group max-w-[85%] ${outgoing ? 'flex flex-col items-end' : ''}`}>
                <div
                  className={`relative max-w-message-bubble min-w-[8rem] rounded-lg px-3 py-3.5 pl-3 pr-10 ${getMessageStyle(
                    message.sender,
                    message.senderName,
                  )}`}
                >
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
                  <p className={`text-sm leading-relaxed break-words whitespace-pre-wrap ${outgoing ? 'text-white' : 'text-text-primary'}`}>
                    {message.content}
                  </p>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <span
                      className={`text-xs ${
                        outgoing ? 'text-white/75' : 'text-text-muted'
                      }`}
                    >
                      {message.timestamp}
                    </span>
                    {isTeamChannel && isStarred && (
                      <Star className={`w-3 h-3 flex-shrink-0 ${outgoing ? 'text-white' : 'text-primary'}`} />
                    )}
                  </div>
                  </div>
                </div>

                {/* React button / reaction: always visible below bubble */}
                <div
                  className={`mt-1 flex gap-1 items-center ${
                    outgoing ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {myReaction ? (
                    <button
                      type="button"
                      onClick={() => setActiveReactionPickerId(message.id)}
                      className="inline-flex items-center justify-center rounded-full border-2 border-primary bg-primary/20 px-2 py-0.5 text-base transition-colors hover:bg-primary/30"
                    >
                      {myReaction}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setActiveReactionPickerId(message.id)}
                      className="p-1 rounded-full bg-white/80 border border-border shadow-sm text-text-muted hover:text-primary hover:border-primary transition-colors"
                      aria-label="React"
                    >
                      <Smile className="w-4 h-4" />
                    </button>
                  )}
                </div>

                {showMenu && (
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

                {showReactions && (
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
            </div>
          );
        })}
      </div>

      {isInternalChat && isDmPage && (
        <div className="border-t border-border px-6 py-2 flex items-center justify-between bg-panel">
          <span className="text-xs text-text-muted">Direct messages</span>
          <div className="flex flex-wrap gap-2 justify-end">
            {internalTeamMembers.map((member) => {
              const isActive = pathname?.startsWith(`/agent/dm/${member.id}`);
              return (
                <Link
                  key={member.id}
                  href={`/agent/dm/${member.id}`}
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                    isActive
                      ? 'bg-primary text-white border-primary'
                      : 'bg-white text-text-secondary border-border hover:bg-panel'
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      isActive ? 'bg-status-success' : 'bg-text-muted'
                    }`}
                  />
                  {member.name}
                </Link>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex-shrink-0 border-t border-border bg-white">
        {/* Reply bar when active */}
        {replyingTo && (
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
        {/* Input row */}
        <div className="flex items-center gap-3 px-4 py-3 min-h-[56px]">
          <button
            type="button"
            className="text-text-secondary hover:text-text-primary flex-shrink-0"
            aria-label="Attach"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
          </button>
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={replyingTo ? `Reply to ${replyingTo.senderName}...` : 'Type a message...'}
            className="flex-1 min-w-0 px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
          />
          <button
            type="button"
            className="bg-primary text-white px-5 py-2.5 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium flex-shrink-0"
            onClick={sendMessage}
          >
            Send
          </button>
        </div>
      </div>

      {(activeMessageMenuId !== null || activeReactionPickerId !== null) && (
        <div
          className="fixed inset-0 z-10"
          onClick={() => {
            setActiveMessageMenuId(null);
            setActiveReactionPickerId(null);
          }}
        />
      )}

      {messageInfoId !== null && (() => {
        const readByList = isInternalChat && teamMemberNames.length > 0
          ? teamMemberNames.map((name, i) => ({
              name,
              readAt: new Date(Date.now() - (i + 1) * 60000 * (i + 2)),
            }))
          : [{ name: title?.split(' ')[0] ? title : 'Customer', readAt: new Date() }];
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
                {readByList.map((reader, idx) => (
                  <div
                    key={reader.name}
                    className={`flex items-center gap-3 px-4 py-3 ${idx > 0 ? 'border-t border-border' : ''}`}
                  >
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold flex-shrink-0">
                      {reader.name.charAt(0)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-text-primary truncate">{reader.name}</p>
                      <p className="text-xs text-text-muted">{formatReadAt(reader.readAt)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      })()}

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
                    {teamMemberNames.map((name) => (
                      <div
                        key={name}
                        className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-panel"
                      >
                        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-semibold">
                          {name[0]}
                        </div>
                        <span className="text-sm text-text-primary">{name}</span>
                      </div>
                    ))}
                  </div>
                )}

                {activeGroupTab === 'media' && (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                        Media
                      </h3>
                      <div className="grid grid-cols-4 gap-2">
                        {Array.from({ length: 8 }).map((_, idx) => (
                          <div
                            key={idx}
                            className="aspect-square rounded-lg bg-panel border border-border flex items-center justify-center text-[10px] text-text-muted"
                          >
                            Image
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                      <div>
                        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                          Links
                        </h3>
                        <ul className="space-y-2 text-sm">
                          <li className="flex items-center gap-2 text-primary cursor-pointer hover:underline">
                            <Link2 className="w-4 h-4" />
                            Tracking dashboard
                          </li>
                          <li className="flex items-center gap-2 text-primary cursor-pointer hover:underline">
                            <Link2 className="w-4 h-4" />
                            Support playbook
                          </li>
                        </ul>
                      </div>
                      <div>
                        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                          Docs
                        </h3>
                        <ul className="space-y-2 text-sm">
                          <li className="flex items-center gap-2 text-text-primary">
                            <FileText className="w-4 h-4 text-text-muted" />
                            SLA-cheatsheet.pdf
                          </li>
                          <li className="flex items-center gap-2 text-text-primary">
                            <FileText className="w-4 h-4 text-text-muted" />
                            Escalation-matrix.docx
                          </li>
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
    </div>
  );
}
