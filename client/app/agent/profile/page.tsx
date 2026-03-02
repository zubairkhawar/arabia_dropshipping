 'use client';

import { useState, ChangeEvent } from 'react';
import { Camera } from 'lucide-react';

export default function AgentProfile() {
  const [fullName, setFullName] = useState('Support Agent');
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);

  const handleAvatarChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setAvatarPreview(reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Profile</h1>
        <p className="text-text-secondary mt-1">Manage your agent profile and settings</p>
      </div>

      <div className="bg-sidebar rounded-lg p-6 border border-border space-y-8">
        {/* Avatar + basic info */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-6">
          <div className="relative">
            <div className="w-28 h-28 sm:w-32 sm:h-32 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden text-2xl font-semibold text-primary">
              {avatarPreview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={avatarPreview} alt="Profile avatar" className="w-full h-full object-cover" />
              ) : (
                fullName.charAt(0).toUpperCase()
              )}
            </div>
            <label className="absolute bottom-1 right-1 inline-flex items-center justify-center w-9 h-9 rounded-full bg-primary text-white shadow-md cursor-pointer hover:bg-primary-dark">
              <Camera className="w-4 h-4" />
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleAvatarChange}
              />
            </label>
          </div>

          <div className="flex-1 space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-primary mb-2">Full Name</label>
              <input
                type="text"
                className="w-full max-w-md px-4 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="Enter your name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
          </div>
        </div>

        {/* Status section (kept from previous version) */}
        <div className="border-t border-border pt-6">
          <h3 className="font-semibold text-text-primary mb-4">Status</h3>
          <div className="flex items-center gap-4">
            <button className="px-4 py-2 bg-status-success text-white rounded-lg text-sm">
              Online
            </button>
            <button className="px-4 py-2 bg-status-warning text-white rounded-lg text-sm">
              Busy
            </button>
            <button className="px-4 py-2 bg-text-muted text-white rounded-lg text-sm">
              Offline
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
