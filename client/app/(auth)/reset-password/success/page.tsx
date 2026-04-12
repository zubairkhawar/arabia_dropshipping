'use client';

import Image from 'next/image';
import Link from 'next/link';

export default function ResetPasswordSuccessPage() {
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
          <div className="w-full max-w-md text-center">
            <div className="bg-sidebar rounded-xl p-8 shadow-sm border border-border space-y-4">
              <h2 className="text-xl font-bold text-text-primary">Password reset successful</h2>
              <p className="text-sm text-text-secondary">
                You can now sign in with your new password.
              </p>
              <Link
                href="/login"
                className="inline-flex w-full justify-center bg-primary text-white py-2.5 px-4 rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium"
              >
                Go to sign in
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
