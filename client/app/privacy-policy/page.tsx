import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Privacy Policy | Arabia Dropshipping',
  description:
    'How Arabia Dropshipping collects, uses, and protects personal information when you use our platform and messaging features.',
};

const sections = [
  {
    title: '1. Introduction',
    body: [
      'Arabia Dropshipping (“we”, “us”, “our”) provides software for ecommerce operations, analytics, and customer support, including optional integrations with messaging channels such as WhatsApp.',
      'This Privacy Policy describes how we handle personal information in connection with our website and application (together, the “Services”). By using the Services, you agree to this policy.',
    ],
  },
  {
    title: '2. Who we are',
    body: [
      'The data controller for information processed through the Services is the Arabia Dropshipping business operating the deployment you use. For privacy-related questions, contact us at the email below.',
    ],
  },
  {
    title: '3. Information we collect',
    body: [
      'Account and profile data: such as name, email address, role, and credentials you provide when you or your organization creates an account.',
      'Support and messaging content: when you connect messaging channels, message content, phone numbers or channel identifiers, and related metadata may be processed to deliver inbox, routing, automation, and support features you configure.',
      'Technical and usage data: such as IP address, device and browser type, approximate location derived from IP, log data, and diagnostic information used to secure and improve the Services.',
      'Ecommerce and integration data: information your organization connects from stores or third-party systems (for example orders, customers, or product data) as permitted by your settings and integrations.',
    ],
  },
  {
    title: '4. WhatsApp and Meta',
    body: [
      'If your organization uses WhatsApp or other Meta products with our Services, Meta also processes data under Meta’s own terms and policies. We process WhatsApp-related data only as needed to provide the features you enable (for example receiving webhooks, displaying conversations, and sending replies on your behalf).',
      'You are responsible for obtaining any required consents and for lawful use of messaging in your jurisdiction.',
    ],
  },
  {
    title: '5. AI-assisted features',
    body: [
      'Some features may use automated or AI-assisted tools to suggest replies, classify requests, or generate content. Inputs you provide (such as message text) may be sent to model providers we use under contractual safeguards, solely to provide the Services.',
    ],
  },
  {
    title: '6. How we use information',
    body: [
      'We use personal information to provide, maintain, and secure the Services; to authenticate users; to process and display data your organization connects; to communicate about the Services; to comply with law; and to improve reliability and performance.',
    ],
  },
  {
    title: '7. Sharing and subprocessors',
    body: [
      'We do not sell your personal information. We may share information with service providers who assist us (for example hosting, databases, email, analytics, or AI infrastructure) under agreements that require appropriate protection.',
      'We may disclose information if required by law, to protect rights and safety, or in connection with a business transfer (such as a merger), subject to applicable law.',
    ],
  },
  {
    title: '8. Security and retention',
    body: [
      'We implement technical and organizational measures designed to protect information against unauthorized access, loss, or misuse. No method of transmission or storage is completely secure.',
      'We retain information for as long as needed to provide the Services, meet legal obligations, resolve disputes, and enforce agreements. Retention periods may depend on your organization’s settings and applicable law.',
    ],
  },
  {
    title: '9. Your rights',
    body: [
      'Depending on where you live, you may have rights to access, correct, delete, or restrict certain processing of your personal information, or to object to processing or to data portability. To exercise these rights, contact us using the email below. You may also have the right to lodge a complaint with a supervisory authority.',
    ],
  },
  {
    title: '10. International transfers',
    body: [
      'We may process information in countries other than your own. Where required, we use appropriate safeguards (such as standard contractual clauses) for transfers of personal data.',
    ],
  },
  {
    title: '11. Children',
    body: [
      'The Services are not directed to children under 16, and we do not knowingly collect their personal information.',
    ],
  },
  {
    title: '12. Changes to this policy',
    body: [
      'We may update this Privacy Policy from time to time. We will post the updated version on this page and revise the “Last updated” date below. Material changes may be communicated through the Services or by email where appropriate.',
    ],
  },
  {
    title: '13. Contact',
    body: [
      'For privacy inquiries: arabiadropshipping05@gmail.com',
    ],
  },
];

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-[#F9FAFB] text-[#0F172A]">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-6 py-4">
          <Link
            href="/login"
            className="text-sm font-medium text-blue-700 hover:text-blue-800 hover:underline"
          >
            ← Back to sign in
          </Link>
          <span className="text-sm font-semibold text-slate-800">Arabia Dropshipping</span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10 pb-16">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Privacy Policy</h1>
        <p className="mt-2 text-sm text-slate-600">Last updated: March 27, 2026</p>

        <div className="mt-10 space-y-10">
          {sections.map((s) => (
            <section key={s.title}>
              <h2 className="text-lg font-semibold text-slate-900">{s.title}</h2>
              <div className="mt-3 space-y-3 text-sm leading-relaxed text-slate-700">
                {s.body.map((p, i) => (
                  <p key={i}>{p}</p>
                ))}
              </div>
            </section>
          ))}
        </div>

        <p className="mt-12 border-t border-slate-200 pt-8 text-xs text-slate-500">
          This policy is provided to support transparency and platform requirements (including app
          listings). It does not constitute legal advice; have qualified counsel review it for your
          specific business and jurisdictions.
        </p>
      </main>
    </div>
  );
}
