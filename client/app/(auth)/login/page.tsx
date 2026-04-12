'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import { Eye, EyeOff } from 'lucide-react';
import {
  AGENT_PORTAL_PREFERS_OFFLINE_KEY,
  clearAuthAgentId,
  writeAuthAgentId,
} from '@/lib/agent-session-storage';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://arabia-dropshipping.onrender.com';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [submittingLogin, setSubmittingLogin] = useState(false);
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    setSubmittingLogin(true);
    try {
      const trimmedEmail = email.trim().toLowerCase();
      const loginBody = new URLSearchParams();
      loginBody.set('username', trimmedEmail);
      loginBody.set('password', password);

      const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: loginBody.toString(),
      });

      if (!loginRes.ok) {
        const data = await loginRes.json().catch(() => ({}));
        throw new Error(data.detail || 'Incorrect email or password');
      }

      const tokenData = (await loginRes.json()) as { access_token: string; token_type: string };
      const authHeader = { Authorization: `Bearer ${tokenData.access_token}` };
      const [meRes, agentMeRes] = await Promise.all([
        fetch(`${API_BASE}/api/auth/me`, { method: 'GET', headers: authHeader }),
        fetch(`${API_BASE}/api/agents/me`, { method: 'GET', headers: authHeader }),
      ]);
      if (!meRes.ok) {
        throw new Error('Could not load account profile');
      }
      const me = (await meRes.json()) as { email: string; role: string };
      const role = (me.role || '').toLowerCase();

      if (typeof window !== 'undefined') {
        localStorage.setItem('auth_token', tokenData.access_token);
        localStorage.setItem('auth_token_type', tokenData.token_type || 'bearer');
        localStorage.setItem('auth_email', me.email || trimmedEmail);
        localStorage.setItem('auth_role', me.role || 'agent');
        if (role === 'agent') {
          if (!agentMeRes.ok) {
            throw new Error('Could not load agent profile');
          }
          const agentMe = (await agentMeRes.json()) as { id: number };
          writeAuthAgentId(String(agentMe.id));
          sessionStorage.removeItem(AGENT_PORTAL_PREFERS_OFFLINE_KEY);
        } else {
          clearAuthAgentId();
        }
        window.dispatchEvent(new Event('auth-changed'));
      }

      if (role === 'admin') {
        router.push('/admin/dashboard');
        return;
      }
      router.push('/agent/inbox');
    } catch (err: any) {
      setLoginError(err?.message || 'Login failed');
    } finally {
      setSubmittingLogin(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background">
      {/* Left side: brand panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-sidebar border-r border-border flex-col justify-between px-10 py-10">
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center text-center max-w-lg">
            <div className="flex items-center gap-5 mb-8">
              <Image
                src="/Arabia_thumbnail.png"
                alt="Arabia"
                width={96}
                height={96}
                className="h-24 w-24"
              />
              <Image
                src="/arabia_logo.png"
                alt="Arabia Dropshipping"
                width={260}
                height={72}
                className="h-18 w-auto"
              />
            </div>
            <p className="text-sm xl:text-base text-text-secondary">
              AI-powered control tower for WhatsApp support and ecommerce order
              operations across your stores.
            </p>
          </div>
        </div>
        <div className="flex items-center justify-center">
          <p className="text-xs text-text-muted">
            © {new Date().getFullYear()} Arabia Dropshipping. All rights reserved.
          </p>
        </div>
      </div>

      {/* Right side: login */}
      <div className="flex-1 flex flex-col px-6 py-6">
        {/* Mobile logo */}
        <div className="flex items-center gap-3 mb-8 lg:hidden">
          <Image
            src="/Arabia_thumbnail.png"
            alt="Arabia"
            width={40}
            height={40}
            className="h-10 w-10"
          />
          <Image
            src="/arabia_logo.png"
            alt="Arabia Dropshipping"
            width={140}
            height={36}
            className="h-9 w-auto"
          />
        </div>

        <div className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-md">
            <>
              <div className="mb-8 lg:mb-10">
                <h2 className="text-2xl font-bold text-text-primary">Sign in</h2>
                <p className="text-sm text-text-secondary mt-1">
                  Use your Arabia credentials to access the workspace.
                </p>
              </div>
              <div className="bg-sidebar rounded-xl p-6 shadow-sm border border-border">
                <form className="space-y-4" onSubmit={handleSubmit}>
                  <div>
                    <label className="block text-sm font-medium text-text-primary mb-2">
                      Email
                    </label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                      placeholder="you@example.com"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-text-primary mb-2">
                      Password
                    </label>
                    <div className="relative">
                      <input
                        type={showLoginPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="w-full pl-4 pr-11 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                        placeholder="Enter your password"
                        required
                        autoComplete="current-password"
                      />
                      <button
                        type="button"
                        onClick={() => setShowLoginPassword((v) => !v)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-panel transition-colors"
                        aria-label={showLoginPassword ? 'Hide password' : 'Show password'}
                      >
                        {showLoginPassword ? (
                          <EyeOff className="w-4 h-4" aria-hidden />
                        ) : (
                          <Eye className="w-4 h-4" aria-hidden />
                        )}
                      </button>
                    </div>
                  </div>
                  <button
                    type="submit"
                    disabled={submittingLogin}
                    className="w-full bg-primary text-white py-2.5 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium"
                  >
                    {submittingLogin ? 'Signing in...' : 'Sign In'}
                  </button>
                  {loginError && <p className="text-xs text-status-error">{loginError}</p>}
                  <Link
                    href="/forgot-password"
                    className="block w-full text-xs text-primary mt-3 hover:underline text-center"
                  >
                    Forgot password?
                  </Link>
                </form>
              </div>
            </>
          </div>
        </div>
      </div>
    </div>
  );
}
