'use client';

import { Suspense, useEffect, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Eye, EyeOff } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://arabia-dropshipping.onrender.com';

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token')?.trim() || '';

  const [verifyPhase, setVerifyPhase] = useState<'loading' | 'valid' | 'invalid'>('loading');
  const [accountEmail, setAccountEmail] = useState('');
  const [invalidMessage, setInvalidMessage] = useState('');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [showPw2, setShowPw2] = useState(false);

  useEffect(() => {
    if (!token) {
      setVerifyPhase('invalid');
      setInvalidMessage('This reset link is missing or incomplete.');
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const url = new URL(`${API_BASE}/api/auth/verify-reset-token`);
        url.searchParams.set('token', token);
        const res = await fetch(url.toString());
        const data = (await res.json()) as {
          valid?: boolean;
          email?: string;
          message?: string;
        };
        if (cancelled) return;
        if (data.valid) {
          setAccountEmail(data.email || '');
          setVerifyPhase('valid');
        } else {
          setInvalidMessage(data.message || 'This reset link is invalid or has expired.');
          setVerifyPhase('invalid');
        }
      } catch {
        if (!cancelled) {
          setInvalidMessage('Could not validate this link. Please try again.');
          setVerifyPhase('invalid');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    if (password.length < 8) {
      setFormMessage('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setFormMessage('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    setFormMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(
          typeof data.detail === 'string' ? data.detail : 'Unable to reset password.',
        );
      }
      router.push('/reset-password/success');
    } catch (err: unknown) {
      setFormMessage(err instanceof Error ? err.message : 'Unable to reset password.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background">
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
              AI-powered control tower for WhatsApp support and ecommerce order operations across
              your stores.
            </p>
          </div>
        </div>
        <div className="flex items-center justify-center">
          <p className="text-xs text-text-muted">
            © {new Date().getFullYear()} Arabia Dropshipping. All rights reserved.
          </p>
        </div>
      </div>

      <div className="flex-1 flex flex-col px-6 py-6">
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
            {verifyPhase === 'loading' && (
              <p className="text-sm text-text-secondary text-center">Checking your reset link…</p>
            )}

            {verifyPhase === 'invalid' && (
              <div className="bg-sidebar rounded-xl p-6 shadow-sm border border-border space-y-4">
                <h2 className="text-xl font-bold text-text-primary">Link not valid</h2>
                <p className="text-sm text-text-secondary">{invalidMessage}</p>
                <Link
                  href="/forgot-password"
                  className="inline-flex w-full justify-center bg-primary text-white py-2.5 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium"
                >
                  Request a new reset link
                </Link>
                <Link
                  href="/login"
                  className="block w-full text-xs text-primary text-center hover:underline"
                >
                  Back to sign in
                </Link>
              </div>
            )}

            {verifyPhase === 'valid' && (
              <>
                <div className="mb-8">
                  <h2 className="text-2xl font-bold text-text-primary">Reset password</h2>
                  <p className="text-sm text-text-secondary mt-1">
                    Choose a new password
                    {accountEmail ? (
                      <>
                        {' '}
                        for <span className="font-medium text-text-primary">{accountEmail}</span>.
                      </>
                    ) : (
                      ' for your Arabia account.'
                    )}
                  </p>
                </div>
                <div className="bg-sidebar rounded-xl p-6 shadow-sm border border-border">
                  <form className="space-y-4" onSubmit={handleSubmit}>
                    <div>
                      <label className="block text-sm font-medium text-text-primary mb-2">
                        New password
                      </label>
                      <div className="relative">
                        <input
                          type={showPw ? 'text' : 'password'}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          className="w-full pl-4 pr-11 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                          placeholder="At least 8 characters"
                          required
                          minLength={8}
                          autoComplete="new-password"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPw((v) => !v)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-panel transition-colors"
                          aria-label={showPw ? 'Hide password' : 'Show password'}
                        >
                          {showPw ? (
                            <EyeOff className="w-4 h-4" aria-hidden />
                          ) : (
                            <Eye className="w-4 h-4" aria-hidden />
                          )}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-text-primary mb-2">
                        Confirm password
                      </label>
                      <div className="relative">
                        <input
                          type={showPw2 ? 'text' : 'password'}
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          className="w-full pl-4 pr-11 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                          placeholder="Re-enter your new password"
                          required
                          minLength={8}
                          autoComplete="new-password"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPw2((v) => !v)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-panel transition-colors"
                          aria-label={showPw2 ? 'Hide password' : 'Show password'}
                        >
                          {showPw2 ? (
                            <EyeOff className="w-4 h-4" aria-hidden />
                          ) : (
                            <Eye className="w-4 h-4" aria-hidden />
                          )}
                        </button>
                      </div>
                    </div>
                    {formMessage && (
                      <p className="text-xs text-status-error bg-panel border border-border rounded-md px-3 py-2">
                        {formMessage}
                      </p>
                    )}
                    <button
                      type="submit"
                      disabled={submitting}
                      className="w-full bg-primary text-white py-2.5 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium disabled:opacity-60"
                    >
                      {submitting ? 'Updating…' : 'Update password'}
                    </button>
                    <Link
                      href="/login"
                      className="block w-full text-xs text-primary text-center hover:underline"
                    >
                      Back to sign in
                    </Link>
                  </form>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-background">
          <p className="text-sm text-text-secondary">Loading…</p>
        </div>
      }
    >
      <ResetPasswordContent />
    </Suspense>
  );
}
