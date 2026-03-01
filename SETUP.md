# Arabia Dropshipping - Setup Guide

## Project Overview

Arabia Dropshipping is a multi-tenant AI-powered ecommerce automation, analytics, and customer support platform with three separate panels:

1. **User Panel** (`/user/*`) - For ecommerce store owners
2. **Agent Panel** (`/agent/*`) - For customer support agents  
3. **Admin Panel** (`/admin/*`) - For system administrators

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.10+
- PostgreSQL (AWS RDS recommended)
- Redis (AWS ElastiCache recommended)

### Frontend Setup

```bash
cd client
npm install
npm run dev
```

Frontend will run on `http://localhost:3000`

### Backend Setup

```bash
cd server
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file (copy from .env.example)
cp .env.example .env
# Edit .env with your configuration

# Run migrations (when Alembic is configured)
alembic upgrade head

# Start server
python run.py
# Or: uvicorn main:app --reload
```

Backend will run on `http://localhost:8000`

## Environment Variables

### Server (.env)

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/arabia_dropshipping
REDIS_URL=redis://localhost:6379/0

# AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# JWT
JWT_SECRET_KEY=your-secret-key-here-change-this
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# OpenAI / LLM
OPENAI_API_KEY=your_openai_api_key

# WhatsApp / WATI
WATI_API_KEY=your_wati_api_key
WATI_API_URL=https://api.wati.io

# Application
ENVIRONMENT=development
DEBUG=True
```

## Project Structure

### Frontend (Next.js)

```
client/
├── app/
│   ├── (auth)/          # Authentication routes
│   ├── user/            # User Panel routes
│   ├── agent/           # Agent Panel routes
│   └── admin/           # Admin Panel routes
├── components/
│   ├── layout/          # Layout components (headers, sidebars)
│   ├── chat/            # Chat components (respond.io style)
│   ├── cards/           # Card components
│   └── charts/          # Chart components
├── lib/                 # Utilities, API clients, hooks
└── public/              # Static assets (logos)
```

### Backend (FastAPI)

```
server/
├── services/            # Microservices
│   ├── auth_service/
│   ├── tenant_service/
│   ├── store_integration_service/
│   ├── analytics_service/
│   ├── ai_orchestrator_service/
│   ├── messaging_service/
│   └── agent_routing_service/
├── models.py           # Centralized database models
├── database.py         # Database connection
├── config.py           # Configuration
└── main.py             # FastAPI app entry
```

## Key Features

### User Panel
- Multi-store management
- Store integrations (Shopify, WooCommerce, Custom API)
- Analytics dashboards
- Chat inbox (view-only)
- Settings

### Agent Panel
- Real-time chat handling
- Multi-channel support (WhatsApp, Web, Portal)
- Online/Busy/Offline status
- Customer context panel
- Conversation management

### Admin Panel
- System monitoring
- Agent management
- Tenant management
- AI performance analytics
- Workflow automation
- Knowledge base management

## Database Schema

Key tables:
- `tenants` - Multi-tenant isolation
- `users` - User accounts (user/agent/admin roles)
- `stores` - Ecommerce store integrations
- `customers` - Customer records
- `orders` - Order tracking
- `conversations` - Chat conversations
- `messages` - Chat messages
- `agents` - Agent profiles
- `routing_rules` - Conversation routing rules

## API Endpoints

### Authentication
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - User logout

### Stores
- `GET /api/stores` - List stores
- `POST /api/stores` - Create store
- `GET /api/stores/{id}` - Get store
- `POST /api/stores/{id}/sync` - Sync store data

### Analytics
- `GET /api/analytics/dashboard` - Dashboard analytics
- `GET /api/analytics/orders` - Order analytics
- `GET /api/analytics/revenue` - Revenue analytics

### AI
- `POST /api/ai/chat` - Process chat message
- `POST /api/ai/verify-customer` - Verify customer
- `POST /api/ai/escalate` - Escalate to agent

### Messaging
- `GET /api/messaging/conversations` - List conversations
- `POST /api/messaging/messages` - Send message
- `WS /api/messaging/ws/{id}` - WebSocket for real-time

## Logo Assets

- `arabia_logo.png` - Main header logo (positioned left)
- `Arabia_thumbnail.png` - Browser tab favicon (positioned right of logo)

Both logos are in `client/public/` and displayed in all panel headers.

## Development Notes

- All UI uses Tailwind CSS utility classes
- No global CSS except minimal reset/base
- Component-based styling only
- Responsive design: mobile, tablet, laptop, desktop, ultra-wide
- Agent Panel uses respond.io-style 3-column layout
- Multi-tenant architecture with strict role isolation

## Next Steps

1. Configure database connection
2. Set up AWS RDS PostgreSQL
3. Set up AWS ElastiCache Redis
4. Configure OpenAI API key
5. Set up WhatsApp integration (WATI)
6. Run database migrations
7. Create initial admin user
8. Test authentication flow
9. Implement store integration APIs
10. Build AI orchestrator pipeline

## Support

For issues or questions, refer to the main README.md file.
