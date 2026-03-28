'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';

const ADMIN_EMAIL = 'arabiadropshipping05@gmail.com';
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://arabia-dropshipping.onrender.com';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showForgot, setShowForgot] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotMessage, setForgotMessage] = useState<string | null>(null);
  const [submittingForgot, setSubmittingForgot] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = email.trim().toLowerCase();

    // Simple role routing: one admin email routes to admin panel, others to agent panel.
    if (trimmedEmail === ADMIN_EMAIL.toLowerCase()) {
      router.push('/admin/dashboard');
    } else {
      router.push('/agent/inbox');
    }
  };

  const handleForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotMessage(null);
    setSubmittingForgot(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: forgotEmail.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Unable to start password reset.');
      }
      setForgotMessage(
        'If an account exists for this email, a reset link has been sent.',
      );
    } catch (err: any) {
      setForgotMessage(err.message || 'Unable to start password reset.');
    } finally {
      setSubmittingForgot(false);
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
        <div className="flex flex-col items-center justify-center gap-2">
          <p className="text-xs text-text-muted">
            © {new Date().getFullYear()} Arabia Dropshipping. All rights reserved.
          </p>
          <Link
            href="/privacy-policy"
            className="text-xs text-primary hover:underline"
          >
            Privacy Policy
          </Link>
        </div>
      </div>

      {/* Right side: login / forgot password */}
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
            {!showForgot ? (
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
                      <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                        placeholder="Enter your password"
                        required
                      />
                    </div>
                    <button
                      type="submit"
                      className="w-full bg-primary text-white py-2.5 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium"
                    >
                      Sign In
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowForgot(true);
                        setForgotEmail(email);
                      }}
                      className="w-full text-xs text-primary mt-3 hover:underline text-center"
                    >
                      Forgot password?
                    </button>
                  </form>
                </div>
              </>
            ) : (
              <>
                <div className="mb-8 lg:mb-10">
                  <h2 className="text-2xl font-bold text-text-primary">
                    Reset your password
                  </h2>
                  <p className="text-sm text-text-secondary mt-1">
                    Enter your email and we&apos;ll send you a reset link.
                  </p>
                </div>
                <div className="bg-sidebar rounded-xl p-6 shadow-sm border border-border">
                  <form className="space-y-4" onSubmit={handleForgot}>
                    <div>
                      <label className="block text-sm font-medium text-text-primary mb-2">
                        Email
                      </label>
                      <input
                        type="email"
                        value={forgotEmail}
                        onChange={(e) => setForgotEmail(e.target.value)}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                        placeholder="you@example.com"
                        required
                      />
                    </div>
                    {forgotMessage && (
                      <p className="text-xs text-text-secondary bg-panel border border-border rounded-md px-3 py-2">
                        {forgotMessage}
                      </p>
                    )}
                    <button
                      type="submit"
                      disabled={submittingForgot}
                      className="w-full bg-primary text-white py-2.5 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium disabled:opacity-60"
                    >
                      {submittingForgot ? 'Sending…' : 'Send reset link'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowForgot(false)}
                      className="w-full text-xs text-primary mt-3 hover:underline text-center"
                    >
                      Back to sign in
                    </button>
                  </form>
                </div>
              </>
            )}
          </div>
        </div>
        <div className="mt-8 flex justify-center lg:hidden">
          <Link href="/privacy-policy" className="text-xs text-primary hover:underline">
            Privacy Policy
          </Link>
        </div>
      </div>
    </div>
  );
}
