import { redirect } from 'next/navigation';

/** Admin chats are only browsed under `/live` or `/closed` (DB-backed lists). */
export default function AdminInboxIndexPage() {
  redirect('/admin/inbox/live');
}
