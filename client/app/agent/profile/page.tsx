'use client';

import { useState, useRef, useEffect } from 'react';
import { Camera, ImagePlus, Trash2, X, Copy } from 'lucide-react';
import { useAgentProfile } from '@/contexts/AgentProfileContext';
import { useAgents } from '@/contexts/AgentsContext';

export default function AgentProfile() {
  const { avatarUrl, fullName, setAvatarUrl, setFullName } = useAgentProfile();
  const { getCurrentAgent } = useAgents();
  const currentAgent = getCurrentAgent();
  const [showAvatarMenu, setShowAvatarMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showAvatarMenu) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node) &&
        !(e.target as HTMLElement).closest('button[data-avatar-trigger]')
      ) {
        setShowAvatarMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showAvatarMenu]);

  const handleChoosePhoto = () => {
    setShowAvatarMenu(false);
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') setAvatarUrl(reader.result);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleDeletePhoto = () => {
    setAvatarUrl(null);
    setShowAvatarMenu(false);
  };

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Profile</h1>
        <p className="text-text-secondary mt-1">Manage your agent profile and settings</p>
      </div>

      <div className="bg-card rounded-xl border border-border shadow-sm p-6 max-w-2xl">
        <div className="flex flex-col sm:flex-row sm:items-center gap-8">
          <div className="relative flex-shrink-0" ref={menuRef}>
            <button
              type="button"
              data-avatar-trigger
              onClick={() => setShowAvatarMenu(!showAvatarMenu)}
              className="relative block w-28 h-28 sm:w-32 sm:h-32 rounded-full overflow-hidden bg-primary/10 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              aria-label="Change profile photo"
            >
              {avatarUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={avatarUrl} alt="Profile" className="w-full h-full object-cover" />
              ) : (
                <span className="w-full h-full flex items-center justify-center text-3xl sm:text-4xl font-semibold text-primary">
                  {fullName.charAt(0).toUpperCase() || '?'}
                </span>
              )}
              <span className="absolute bottom-0 right-0 w-9 h-9 rounded-full bg-primary text-white flex items-center justify-center shadow-md">
                <Camera className="w-4 h-4" />
              </span>
            </button>

            {showAvatarMenu && (
              <div className="absolute left-0 top-full mt-2 z-20 w-52 bg-white border border-border rounded-xl shadow-xl py-1">
                <button
                  type="button"
                  onClick={handleChoosePhoto}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm text-text-primary hover:bg-panel"
                >
                  <ImagePlus className="w-5 h-5 text-text-muted" />
                  Choose photo
                </button>
                {avatarUrl && (
                  <button
                    type="button"
                    onClick={handleDeletePhoto}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm text-status-error hover:bg-panel"
                  >
                    <Trash2 className="w-5 h-5" />
                    Delete photo
                  </button>
                )}
                <div className="border-t border-border my-1" />
                <button
                  type="button"
                  onClick={() => setShowAvatarMenu(false)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm text-text-muted hover:bg-panel"
                >
                  <X className="w-5 h-5" />
                  Cancel
                </button>
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          <div className="flex-1 min-w-0 space-y-4">
            <div>
              <label className="block text-sm font-semibold text-text-primary mb-2">Full Name</label>
              <input
                type="text"
                className="w-full max-w-md px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary text-text-primary placeholder-text-muted"
                placeholder="Enter your name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
            {currentAgent?.id && (
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">Agent ID</label>
                <div className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-panel">
                  <code className="text-sm font-mono text-text-primary">{currentAgent.id}</code>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(currentAgent.id)}
                    className="p-1.5 rounded-lg hover:bg-white text-text-muted transition-colors"
                    aria-label="Copy agent ID"
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
