# Arabia Dropshipping Platform — Project Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ARABIA DROPSHIPPING PLATFORM                             │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │   Admin Panel   │    │   Agent Panel   │    │   AI Bot        │         │
│  │  (Control)      │    │  (Support)      │    │  (Customer)     │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│           └──────────────────────┼──────────────────────┘                   │
│                                  │                                          │
│                          ┌───────▼───────┐                                  │
│                          │  PostgreSQL   │                                  │
│                          │   Database    │                                  │
│                          └───────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: Admin Panel

### Purpose

Manage the entire platform: agents, teams, knowledge base, broadcasts, and monitoring.

### Key features

| Feature | Description |
|--------|-------------|
| Agent Management | Create, edit, delete agents. Set passwords, teams, max concurrent chats |
| Team Management | Create teams, assign agents, transfer agents between teams |
| Knowledge Base | Upload PDFs, add URLs, manage API sources for AI bot |
| Broadcast Messages | Schedule festival/occasion messages for AI context |
| Conversation Monitoring | View all live/closed conversations (read-only) |
| Agent Attendance | Track agent login/logout, working hours, generate PDF reports |
| Settings | Timezone, OpenAI API key, agent management defaults |

### Admin workflows

**Creating an agent**

```
Admin clicks "Add Agent"
         │
         ▼
Enters: Name, Email, Password, Team, Max Chats
         │
         ▼
System creates User record (hashed password)
         │
         ▼
System creates Agent record linked to User
         │
         ▼
Agent receives email with credentials
```

**Managing knowledge base**

```
Admin uploads PDF or adds URL
         │
         ▼
System extracts text, chunks, stores
         │
         ▼
Status: INDEXING → READY
         │
         ▼
Bot can now answer from KB
```

**Monitoring conversations**

```
Admin views All Conversations
         │
         ▼
Sees every chat (live, closed, transferred)
         │
         ▼
Can read but cannot reply (read-only)
         │
         ▼
Can transfer conversations to agents
```

---

## Part 2: Agent Panel

### Purpose

Handle customer conversations via WhatsApp, collaborate internally via team channels and DMs.

### Key features

| Feature | Description |
|--------|-------------|
| Inbox (My Chats) | Customer conversations assigned to agent |
| Team Channels | Group chat with other agents |
| Direct Messages | Private chat with another agent |
| Notifications | Real-time alerts for mentions, transfers, new messages |
| Voice Notes | Send voice messages in internal chats (not to customers) |
| Message Actions | Edit, delete, copy, react, reply |
| Search | Search within conversations |
| Attendance | Auto-tracked login/logout time |

### Agent workflows

**Handling customer chat**

```
Customer sends WhatsApp message
         │
         ▼
AI bot answers (if not escalated)
         │
         ▼
If customer says "agent" → routed to available agent
         │
         ▼
Agent sees chat in Live Conversations
         │
         ▼
Agent replies → Customer receives on WhatsApp
         │
         ▼
Agent can transfer, close, or send back to AI
```

**Internal collaboration**

```
Agent opens Team Channel
         │
         ▼
Types message with @mention
         │
         ▼
Mentioned agent gets notification
         │
         ▼
All team members see message in real-time
```

**Voice notes (internal only)**

```
Agent clicks mic button (in team/DM only)
         │
         ▼
Records voice (max 120 sec)
         │
         ▼
Reviews and sends
         │
         ▼
Other agents receive playable voice note
```

---

## Part 3: AI Bot

### Purpose

Answer customer questions automatically, escalate to agents when needed.

### Customer flow

```
Customer sends WhatsApp message
         │
         ▼
WhatsApp webhook → Your server
         │
         ▼
Check: Is conversation assigned to agent?
         │
         ├── Yes → Forward to agent, bot silent
         │
         └── No → Bot processes message
                      │
                      ▼
              ┌─────────────────────────────────────┐
              │         Intent Detection            │
              ├─────────────────────────────────────┤
              │ • "agent" / "human" → Escalate       │
              │ • Order question → Order flow        │
              │ • Account question → Verification    │
              │ • General question → Knowledge Base  │
              │ • "reset" → Clear session            │
              └─────────────────────────────────────┘
                      │
                      ▼
              ┌─────────────────────────────────────┐
              │         Knowledge Base              │
              ├─────────────────────────────────────┤
              │ • PDF documents                     │
              │ • Website URLs                      │
              │ • API sources                       │
              │ • Chunked and retrieved via scoring │
              └─────────────────────────────────────┘
                      │
                      ▼
              ┌─────────────────────────────────────┐
              │         LLM (OpenAI)                │
              ├─────────────────────────────────────┤
              │ • Generates natural response        │
              │ • Uses KB context                   │
              │ • Matches user language             │
              │ • Provides source attribution       │
              └─────────────────────────────────────┘
                      │
                      ▼
              Customer receives answer
```

### Verification flow (existing customer)

```
Customer: "Where is my order?"
         │
         ▼
Bot: "Please send your email address"
         │
         ▼
Customer: "john@example.com"
         │
         ▼
Bot calls: POST /customers/send-verification-code
         │
         ▼
Bot: "Code sent to john@example.com. Please enter it."
         │
         ▼
Customer: "123456"
         │
         ▼
Bot calls: POST /customers/verify-code
         │
         ▼
Bot: "Please confirm your mobile number"
         │
         ▼
Customer: "971555516304"
         │
         ▼
Bot calls: GET /customers?email=john@example.com&mobile=971555516304
         │
         ▼
Response: seller_id = 12345
         │
         ▼
Bot stores verified = true, expires in 3 days
         │
         ▼
Bot: "Order #12345 is in transit. Expected Friday."
```

### Knowledge base retrieval

```
Customer: "What is your return policy?"
         │
         ▼
Bot tokenizes question
         │
         ▼
Scores each KB chunk for relevance
         │
         ▼
Selects top chunks (min_score configurable)
         │
         ▼
Builds prompt with knowledge_context
         │
         ▼
LLM answers: "Returns accepted within 14 days..."
         │
         ▼
Includes source: https://www.arabiadropship.com
```
