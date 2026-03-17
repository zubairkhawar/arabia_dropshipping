from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from services.auth_service.api import router as auth_router
from services.tenant_service.api import router as tenant_router
from services.store_integration_service.api import router as store_router
from services.analytics_service.api import router as analytics_router
from services.ai_orchestrator_service.api import router as ai_router
from services.messaging_service.api import router as messaging_router
from services.agent_routing_service.api import router as routing_router
from services.agents_service.api import router as agents_router
from services.teams_service.api import router as teams_router
from services.notifications_service.api import router as notifications_router
from services.broadcasts_service.api import router as broadcasts_router
from services.knowledge_service.api import router as knowledge_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Arabia Dropshipping API",
    description="AI-powered ecommerce automation, analytics, and customer support platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://arabia-dropshipping.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(tenant_router, prefix="/api/tenants", tags=["tenants"])
app.include_router(store_router, prefix="/api/stores", tags=["stores"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
app.include_router(ai_router, prefix="/api/ai", tags=["ai"])
app.include_router(messaging_router, prefix="/api/messaging", tags=["messaging"])
app.include_router(routing_router, prefix="/api/routing", tags=["routing"])
app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
app.include_router(teams_router, prefix="/api/teams", tags=["teams"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])
app.include_router(broadcasts_router, prefix="/api", tags=["broadcasts"])
app.include_router(knowledge_router, prefix="/api/knowledge", tags=["knowledge"])


@app.get("/")
async def root():
    return {"message": "Arabia Dropshipping API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
