# Arabia Dropshipping

AI-powered ecommerce automation, analytics, and customer support platform.

## Project Structure

```
Arabia Dropshipping/
├── client/                 # Next.js Frontend
│   ├── app/               # App Router
│   │   ├── (auth)/        # Authentication routes
│   │   ├── user/          # User Panel (Client Portal)
│   │   ├── agent/         # Agent Panel (Support Agents)
│   │   └── admin/         # Admin Panel (System Administrators)
│   ├── components/        # React Components
│   │   ├── layout/        # Layout components
│   │   ├── chat/          # Chat components
│   │   ├── cards/         # Card components
│   │   └── charts/        # Chart components
│   ├── lib/               # Utilities and helpers
│   └── public/            # Static assets
│
└── server/                # FastAPI Backend
    ├── services/          # Microservices
    │   ├── auth_service/
    │   ├── tenant_service/
    │   ├── store_integration_service/
    │   ├── analytics_service/
    │   ├── ai_orchestrator_service/
    │   ├── messaging_service/
    │   └── agent_routing_service/
    ├── main.py            # FastAPI application entry
    └── config.py          # Configuration
```

## Three Panel System

### 1. User Panel (`/user/*`)
- **Role**: Ecommerce Store Owners
- **Features**: Store management, analytics, integrations, chat monitoring

### 2. Agent Panel (`/agent/*`)
- **Role**: Customer Support Agents
- **Features**: Live chat handling, conversation management, customer context
- **Layout**: respond.io-style 3-column layout

### 3. Admin Panel (`/admin/*`)
- **Role**: System Administrators
- **Features**: System monitoring, agent management, tenant management, AI analytics

## Tech Stack

### Frontend
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- React Hooks

### Backend
- FastAPI
- PostgreSQL (AWS)
- Redis (AWS)
- LangChain + LangGraph
- SQLAlchemy
- Alembic

## Getting Started

### Frontend Setup

```bash
cd client
npm install
npm run dev
```

### Backend Setup

```bash
cd server
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/arabia_dropshipping
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET_KEY=your-secret-key-here

# OpenAI
OPENAI_API_KEY=your_openai_api_key
```

## Logo Assets

- `arabia_logo.png` - Main header logo (left)
- `Arabia_thumbnail.png` - Browser tab favicon (right of logo)

## License

Proprietary - Arabia Dropshipping
