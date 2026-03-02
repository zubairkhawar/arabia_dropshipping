# Arabia Dropshipping

AI-powered ecommerce automation, analytics, and customer support platform.

## Project Structure

```
Arabia Dropshipping/
├── client/                 # Next.js Frontend
│   ├── app/               # App Router
│   │   ├── (auth)/        # Authentication routes
│   │   ├── agent/         # Agent Portal (Support Agents)
│   │   └── admin/         # Admin Portal (System Administrators)
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

## Portal & Channel Structure

### 1. Agent Portal (`/agent/*`)
- **Role**: Customer Support Agents
- **Features**: Live chat handling, conversation management, customer context
- **Layout**: respond.io-style 3-column layout

### 2. Admin Portal (`/admin/*`)
- **Role**: System Administrators
- **Features**: System monitoring, agent management, tenant management, AI analytics

### 3. Customer Channel (WhatsApp)
- **Role**: End customers
- **Features**: Interact only through WhatsApp; store/customer data is fetched from client APIs and used by the AI bot and agents, not exposed via a separate web user portal

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
