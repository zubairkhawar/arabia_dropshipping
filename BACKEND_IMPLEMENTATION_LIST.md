# Backend Implementation List

This document lists every frontend feature, button, and flow that requires backend implementation. It is derived from the admin panel, agent panel, and shared UI.

---

## 1. Authentication & Authorization

| Feature | Location | Backend need |
|--------|----------|--------------|
| **Login** | `(auth)/login` | Implement `POST /api/auth/login` (OAuth2PasswordRequestForm). Validate credentials, return JWT. Frontend currently routes by email (admin vs agent); backend should return role and redirect path or let frontend use role from token. |
| **Register** | Referenced | Implement `POST /api/auth/register` (admin-only or invite-only in many setups). |
| **Logout** | Agent header dropdown | Optional: `POST /api/auth/logout` to invalidate token/refresh; or client-side token clear only. |
| **Get current user** | Any authenticated page | Implement `GET /api/auth/me` (token → user + role + agent_id if agent). Used to hydrate profile, permissions, agent id. |
| **Forgot password** | Login page "Forgot?" | ✅ Implemented: `POST /api/auth/forgot-password`. Complete email sending (e.g. SES) for reset link. |
| **Reset password** | `(auth)/reset-password` | ✅ Implemented: `POST /api/auth/reset-password` with token + new password. |
| **Agent change password** | Agent header → Change password popup | New: Verify old password, update user's hashed_password for the logged-in agent (link User to Agent, update User). Optional: `PUT /api/auth/me/password` with `old_password`, `new_password`. |

---

## 2. Admin Panel

### 2.1 Dashboard (`/admin/dashboard`)

| Feature | Backend need |
|--------|----------------|
| **Total Messages** KPI | Aggregate count of messages (e.g. last 7/30 days). Endpoint e.g. `GET /api/analytics/dashboard` returning `total_messages`, `total_messages_change_percent`. |
| **AI Handled** KPI | Count/percent of messages where `sender_type = 'ai'` or conversations resolved by AI. Same dashboard endpoint. |
| **Total Agents** | Count of agents (or users with role=agent). Can be from existing agents API or dashboard. |
| **Active Agents** | Count of agents with `status = 'online'` (or online in last N minutes). Real-time or cached. |
| **Agent Activity chart** | Time-series (e.g. per day) of active/busy agent counts. `GET /api/analytics/agent-activity?from=&to=` or part of dashboard. |
| **Language Distribution** pie chart | Aggregate detected language of messages or conversations. `GET /api/analytics/language-distribution` or part of dashboard. |

### 2.2 Agents (`/admin/agents`)

| Feature | Backend need |
|--------|----------------|
| **List agents** | `GET /api/agents` or equivalent (tenant-scoped). Return id, email, name, avatar_url, status, team; map to `User` + `Agent` in DB. |
| **Add agent** | `POST /api/agents` with email, name, password. Create User (role=agent) + Agent row, return agent id. |
| **Edit agent name** | `PATCH /api/agents/:id` with name (and optionally email, avatar). Update User.full_name and/or Agent. |
| **Remove agent** | `DELETE /api/agents/:id`. Deactivate or delete User/Agent; handle existing conversation reassignment. |
| **Agent password** | Stored in frontend (AgentsContext) for demo. Backend should store hashed password on User; admin may need "reset password" or "send invite" instead of plaintext. |
| **Uptime % / Avg response time** | Mock in frontend. Backend: compute from presence logs and message timestamps (first agent reply after customer message). `GET /api/agents/:id/stats` or include in agent detail. |
| **Attendance / working days** | Frontend uses `OnlineScheduleContext` (working days/hours). Persist per-tenant: `GET/PUT /api/tenants/:id/schedule` or settings. |
| **Download agent report (PDF)** | Frontend builds PDF from local attendance data. Backend: provide attendance data for agent and date range: `GET /api/agents/:id/attendance?year=&month=` (list of days with status/hours). |
| **Download all agents report** | Same: backend endpoint to return attendance (or summary) for all agents for a month. |

### 2.3 Teams (`/admin/teams`)

| Feature | Backend need |
|--------|----------------|
| **List teams** | `GET /api/teams` (tenant-scoped). Teams table or equivalent; members as list of user/agent ids or names. |
| **Create team** | `POST /api/teams` with name, description. |
| **Delete team** | `DELETE /api/teams/:id`. Handle: unassign agents from team, or prevent if agents still assigned. |
| **Add member to team** | `POST /api/teams/:id/members` with agent_id or email. Update Agent.team or junction table. |
| **Remove member from team** | `DELETE /api/teams/:id/members/:agent_id` (or by identifier). |
| **Transfer member** | `POST /api/teams/transfer` or PATCH: member from team A to team B. Update Agent.team. |
| **Team events** | Frontend stores events (member_added, member_removed, member_transferred) in context. Backend: persist audit log or events table; `GET /api/teams/:id/events` for timeline. |

### 2.4 Admin Inbox (`/admin/inbox`, `/admin/inbox/live`, `/admin/inbox/closed`)

| Feature | Backend need |
|--------|----------------|
| **Conversation list** | `GET /api/conversations` (or messaging) with filters: status=active|resolved, agent_id, team, store_id, date range. Return list with customer_name, last_message, last_activity_at, channel, status, handler (AI/agent), handler_name, closed_at, etc. |
| **Read-only chat view** | Same as agent: get conversation + messages. `GET /api/messaging/conversations/:id` with messages. |
| **Context panel** | Customer info, store details, assignment, live analytics. Backend: conversation detail endpoint to include customer, store, assigned agent, and optionally live stats (AI resolution rate, agent load, at-risk count). |

### 2.5 Settings (`/admin/settings`)

| Feature | Backend need |
|--------|----------------|
| **OpenAI API key** | ✅ Implemented: `GET/POST /api/ai/openai-config`. Store in env or secure vault per tenant. |
| **OpenAI usage** | ✅ Implemented: `GET /api/ai/openai-usage`. |
| **Agent online schedule** | Working days (0–6) and start/end time. Persist: `GET/PUT /api/tenants/:id/schedule` or `/api/settings/schedule`. Used by agent panel to allow "online" only within schedule. |
| **Save Changes (schedule)** | Persist schedule to backend when "Save Changes" clicked. |
| **AI Broadcast Messages** | Add/remove/list broadcasts. Backend: `GET/POST/DELETE /api/broadcasts` (tenant-scoped). Fields: title, message, occasion, starts_at, ends_at. AI orchestrator reads active broadcast when generating "agent availability" replies. |
| **Cancel/End broadcast** | `DELETE /api/broadcasts/:id` or PATCH to mark ended. |

### 2.6 Knowledge Base (`/admin/knowledge-base`)

| Feature | Backend need |
|--------|----------------|
| **Upload files** | `POST /api/knowledge/sources` with file(s). Store file, chunk, embed, and index in vector DB. Return source id, status (indexing/ready), chunk count. |
| **Add URL source** | `POST /api/knowledge/sources` with type=url, url. Crawl, chunk, embed, index. |
| **Add API source** | `POST /api/knowledge/sources` with type=api, name, url, auth (none/api_key/bearer), headers, refresh_interval, schema_notes. Sync job to pull, transform, chunk, index. |
| **List sources** | `GET /api/knowledge/sources`. Return id, name, type, status, chunks, last_updated. |
| **Remove source** | `DELETE /api/knowledge/sources/:id`. Remove from vector store and metadata. |
| **Status / chunks** | Part of list or detail; optional webhook or poll for "indexing" → "ready". |

---

## 3. Agent Panel

### 3.1 Agent Inbox (`/agent/inbox`)

| Feature | Backend need |
|--------|----------------|
| **Conversation list** | `GET /api/conversations` filtered by assigned agent (current user’s agent_id), or by team. Include status (active/resolved), last_message, last_activity_at, unread count, channel, is_new_lead, reopened_at, handler info. |
| **Select conversation** | Load messages for conversation: `GET /api/messaging/conversations/:id` with messages (paginated if needed). |
| **Send message** | `POST /api/messaging/messages` with conversation_id, content, sender_type=agent. Persist message; optionally push to customer (WhatsApp) and to real-time for other clients. |
| **Send back to AI** | Update conversation: set handler to AI (clear agent_id or set status), add system message "Conversation sent back to AI bot." Backend: `POST /api/conversations/:id/send-to-ai` or PATCH conversation. |
| **Transfer to team member** | Update conversation’s agent_id to target agent; add system message "Conversation transferred to X by Y"; create notification for target agent. Backend: `POST /api/conversations/:id/transfer` with target_agent_id, optional note. Persist message and notification. |
| **Close conversation** | Set conversation status to resolved, set closed_at; add system message "Conversation closed by agent." Backend: `PATCH /api/conversations/:id` (status=resolved) and append system message. |
| **Reopen (customer messaged again)** | When new inbound message arrives for a resolved conversation: set status=active, set reopened_at, keep same agent_id, add soft message "Customer messaged again." Backend: in WhatsApp webhook or message ingestion, detect existing resolved conversation by customer/phone, reopen and append message; notify frontend (WebSocket or poll). |
| **Context panel** | Customer info, store details, internal notes. Backend: conversation detail includes customer, store; `GET/POST /api/conversations/:id/notes` for internal notes. |
| **Save internal note** | `POST /api/conversations/:id/notes` or PATCH. Persist and return. |

### 3.2 Notifications (`/agent/settings` – Notifications page)

| Feature | Backend need |
|--------|----------------|
| **List notifications** | `GET /api/notifications` (for current agent). Return id, type (chat_transfer, new_lead, new_message, personal_message), message, description, from_agent_id, from_agent_name, conversation_id, conversation_customer_name, created_at, read. |
| **Mark as read** | `PATCH /api/notifications/:id` (read=true) or `POST /api/notifications/:id/read`. |
| **Mark all as read** | `POST /api/notifications/read-all`. |
| **Create on transfer** | When transfer is done, backend creates notification for target agent (to_agent_id). |
| **Create on new lead / new message** | When conversation is assigned to agent or new message in assigned conversation, create notification. |
| **Unread count** | Part of `GET /api/notifications` or `GET /api/notifications/unread-count`. |

### 3.3 Profile & Change Password (header dropdown)

| Feature | Backend need |
|--------|----------------|
| **Profile data** | Name, email, agent ID from current user + agent. `GET /api/auth/me` (or `/api/agents/me`) returning user + linked agent. |
| **Update name** | `PATCH /api/auth/me` or `PATCH /api/agents/me` with full_name/name. |
| **Update avatar** | `POST /api/auth/me/avatar` or agents/me avatar upload; store URL. |
| **Change password** | `PUT /api/auth/me/password` with old_password, new_password. Verify old, update hashed_password. |

### 3.4 Agent Status (header)

| Feature | Backend need |
|--------|----------------|
| **Set status (Active/Offline)** | `POST /api/routing/agents/:id/status` with status=online|offline|busy. ✅ Exists; frontend must call it when agent toggles status (and use schedule to disable "Active" outside hours). |
| **Working schedule** | Fetched from backend (see Admin Settings schedule). Agent panel uses it to allow "Active" only within working days/hours. |

### 3.5 Activity (`/agent/activity`)

| Feature | Backend need |
|--------|----------------|
| **Conversation history / stats** | `GET /api/agents/me/activity` or `/api/conversations?agent_id=me` with summary stats (conversations handled, resolution rate, etc.). |

### 3.6 Team Channel (`/agent/team`)

| Feature | Backend need |
|--------|----------------|
| **Team channel messages** | Internal channel per team. Backend: channel or conversation type=internal_team, team_id. `GET /api/teams/:id/channel/messages`, `POST /api/teams/:id/channel/messages`. |
| **Team events** | Member added/removed/transferred (see Teams). Shown as soft messages in channel. |

### 3.7 Direct Messages (`/agent/dm`, `/agent/dm/[slug]`)

| Feature | Backend need |
|--------|----------------|
| **List DMs** | Conversations between current agent and other agents. `GET /api/dms` or internal conversations with type=dm, participant_ids. |
| **DM messages** | `GET /api/dms/:slug_or_id/messages`, `POST /api/dms/:slug_or_id/messages`. |
| **Create DM** | When opening a DM with another agent, create or get conversation. `POST /api/dms` with other_agent_id. |

---

## 4. Messaging & Conversations (shared)

| Feature | Backend need |
|--------|----------------|
| **List conversations** | `GET /api/messaging/conversations` (or `/api/conversations`) with query params: tenant_id, status, agent_id, team, channel, from, to. Pagination. |
| **Get conversation + messages** | `GET /api/messaging/conversations/:id` with nested messages (or separate `GET /api/messaging/conversations/:id/messages`). Include customer, store, assignment, tags. |
| **Create conversation** | When new customer message arrives (e.g. WhatsApp webhook), create conversation and first message. |
| **Send message** | `POST /api/messaging/messages` with conversation_id, content, sender_type (customer|agent|ai), sender_id (if agent). Persist; trigger AI if needed; push to channel (WhatsApp) and real-time. |
| **WhatsApp webhook** | ✅ Entry exists: receive inbound, run AI orchestrator, return reply. Implement: create/find conversation, store message, send reply via WhatsApp provider, escalate to agent if needed (call routing assign, create notification). |
| **Reopen on new message** | In webhook or message pipeline: if conversation exists and status=resolved, reopen (status=active, reopened_at), append "Customer messaged again" system message, notify assigned agent. |

---

## 5. Real-time / WebSocket (optional but recommended)

| Feature | Backend need |
|--------|----------------|
| **Agent presence** | WebSocket or SSE: agent goes online/offline/busy. Broadcast to admin and other agents. Or poll `GET /api/routing/agents` for status. |
| **New message** | When a message is created, push to relevant clients (assigned agent, admin inbox). |
| **New conversation / assignment** | When conversation is assigned to agent, push so agent inbox updates and notification appears. |
| **Notifications** | Push new notification to agent when created (transfer, new lead, new message). |

---

## 6. Tenants & Multi-tenancy

| Feature | Backend need |
|--------|----------------|
| **Tenant context** | All APIs scoped by tenant_id (from JWT or subdomain). Ensure agents, conversations, stores, teams, settings are tenant-isolated. |
| **Tenant settings** | Schedule, broadcasts, OpenAI key (if per-tenant) under tenant. |

---

## 7. Already Implemented (summary)

- **Auth:** Forgot password, reset password (JWT + DB).
- **AI:** OpenAI config (get/set key), OpenAI usage.
- **Routing:** List agents, update agent status, assign conversation, transfer conversation (stubs or full logic in `agent_routing_service`).
- **Messaging:** WhatsApp webhook entry (AI reply); conversation/message CRUD stubbed.
- **Models:** Tenant, User, Store, Customer, Order, Agent, Conversation, Message, RoutingRule, StoreAgentMapping.

---

## 8. Suggested API Surface (concise)

- `POST /api/auth/login`, `GET /api/auth/me`, `PUT /api/auth/me`, `PUT /api/auth/me/password`
- `GET/PUT /api/tenants/:id/schedule`
- `GET /api/agents`, `POST /api/agents`, `PATCH /api/agents/:id`, `DELETE /api/agents/:id`, `GET /api/agents/me`, `GET /api/agents/:id/attendance`
- `GET /api/teams`, `POST /api/teams`, `DELETE /api/teams/:id`, `POST /api/teams/:id/members`, `DELETE /api/teams/:id/members/:agent_id`, `POST /api/teams/transfer`, `GET /api/teams/:id/events`
- `GET /api/messaging/conversations`, `GET /api/messaging/conversations/:id`, `POST /api/messaging/conversations/:id/messages` (or `/messages` global with conversation_id), `POST /api/conversations/:id/transfer`, `POST /api/conversations/:id/send-to-ai`, `PATCH /api/conversations/:id` (close/reopen), `GET/POST /api/conversations/:id/notes`
- `GET /api/notifications`, `PATCH /api/notifications/:id`, `POST /api/notifications/read-all`
- `GET /api/broadcasts`, `POST /api/broadcasts`, `DELETE /api/broadcasts/:id`
- `GET /api/analytics/dashboard`, `GET /api/analytics/agent-activity`, `GET /api/analytics/language-distribution`
- `GET /api/knowledge/sources`, `POST /api/knowledge/sources`, `DELETE /api/knowledge/sources/:id`
- `GET /api/dms`, `GET /api/dms/:id/messages`, `POST /api/dms/:id/messages` (and create DM if needed)

Use this list to prioritize and implement backend endpoints and behaviors so the admin and agent panels work end-to-end with real data.
