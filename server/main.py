from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi.responses import FileResponse
from config import hydrate_openai_api_key_from_db, settings
from database import (
    SessionLocal,
    engine,
    Base,
    ensure_broadcast_delivery_columns,
    ensure_broadcast_whatsapp_template_columns,
    ensure_team_channel_admin_sender_columns,
    ensure_team_channel_read_states_table,
    ensure_agent_read_state_tables,
    ensure_tenant_display_timezone_column,
    ensure_tenant_openai_api_key_column,
    ensure_user_avatar_url_column,
    ensure_agent_plaintext_password_column,
    ensure_agent_accepting_chats_column,
    ensure_tenant_agent_management_columns,
    ensure_message_enhancements,
    ensure_dm_team_message_metadata_json,
    ensure_pgvector_extension,
    ensure_trending_product_image_arrays,
    ensure_trending_product_unit_pieces_column,
    ensure_trending_product_is_trending_column,
    ensure_whatsapp_broadcast_tables,
    ensure_user_emails_lowercased,
)
from models import Tenant, User
from services.auth_service.services import get_password_hash

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
from services.broadcasts_service.templates_api import router as wa_templates_router
from services.broadcasts_service.campaigns_api import router as broadcast_campaigns_router
from services.admin_realtime_service.api import router as admin_realtime_router
from services.knowledge_service.api import router as knowledge_router
from services.internal_dm_service.api import router as internal_dm_router
from services.agent_portal_service.api import router as agent_portal_router
from services.orders_export_service.api import router as orders_export_router
from services.invoices_export_service.api import router as invoices_export_router
from services.upload_service.api import router as upload_router
from services.trending_products_service.api import (
    public_router as trending_public_router,
    router as trending_products_admin_router,
    trending_page_router,
)

logger = logging.getLogger(__name__)


async def _broadcast_agent_enforcement_loop() -> None:
    """While an AI-targeted broadcast window is active, keep tenant agents offline."""
    from database import SessionLocal
    from services.broadcasts_service.broadcast_agent_lock import (
        run_broadcast_agent_enforcement_tick_async,
    )

    await asyncio.sleep(15)
    while True:
        try:
            db = SessionLocal()
            try:
                await run_broadcast_agent_enforcement_tick_async(db)
            finally:
                db.close()
        except Exception:
            logger.exception("broadcast_agent_enforcement_loop tick failed")
        await asyncio.sleep(60)


async def _stale_chat_release_loop() -> None:
    """
    Periodically release conversations that have been assigned to an agent
    with no agent reply for ``agent_chat_stale_release_hours`` (default 24h).
    Safety net for the case where an agent disappears permanently — without
    this they could hold customer chats hostage now that we no longer auto-
    offline on WebSocket disconnect.
    """
    hours = int(getattr(settings, "agent_chat_stale_release_hours", 0) or 0)
    if hours <= 0:
        return
    interval = int(getattr(settings, "agent_chat_stale_check_interval_seconds", 300) or 0)
    if interval <= 0:
        return
    from services.messaging_service.stale_chat_release import run_stale_chat_release_tick

    await asyncio.sleep(30)
    while True:
        try:
            count = await run_stale_chat_release_tick()
            if count:
                logger.info("stale_chat_release_loop: released %s conversations", count)
        except Exception:
            logger.exception("stale_chat_release_loop tick failed")
        await asyncio.sleep(interval)


async def _memory_stats_background_loop() -> None:
    """Periodic Redis INFO logging for ops (non-blocking; failures are logged only)."""
    if not bool(getattr(settings, "memory_stats_log_enabled", True)):
        return
    interval = int(getattr(settings, "memory_stats_log_interval_seconds", 86400) or 0)
    if interval <= 0:
        return
    delay = int(getattr(settings, "memory_stats_initial_delay_seconds", 120) or 0)
    if delay > 0:
        await asyncio.sleep(delay)
    from services.memory_cleanup import log_memory_stats

    while True:
        try:
            log_memory_stats()
        except Exception:
            logger.exception("memory_stats background task failed")
        await asyncio.sleep(interval)


def ensure_admin_user() -> None:
    """
    Create a default tenant (id=1) and an admin user from env vars if they don't exist.
    """
    if not settings.admin_email or not settings.admin_password:
        return

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == 1).first()
        if tenant is None:
            tenant = Tenant(
                id=1,
                name="Default Tenant",
                domain=None,
                display_timezone="Asia/Karachi",
                is_active=True,
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
        elif not getattr(tenant, "display_timezone", None):
            tenant.display_timezone = "Asia/Karachi"
            db.add(tenant)
            db.commit()

        admin_email = (settings.admin_email or "").strip().lower()
        existing = db.query(User).filter(User.email == admin_email).first()
        if existing:
            return

        user = User(
            tenant_id=tenant.id,
            email=admin_email,
            full_name="Arabia Admin",
            role="admin",
            hashed_password=get_password_hash(settings.admin_password),
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    memory_stats_task: Optional[asyncio.Task] = None
    broadcast_agent_task: Optional[asyncio.Task] = None
    Base.metadata.create_all(bind=engine)
    ensure_broadcast_delivery_columns()
    ensure_broadcast_whatsapp_template_columns()
    ensure_team_channel_admin_sender_columns()
    ensure_team_channel_read_states_table()
    ensure_agent_read_state_tables()
    ensure_tenant_display_timezone_column()
    ensure_tenant_openai_api_key_column()
    ensure_user_avatar_url_column()
    ensure_agent_plaintext_password_column()
    ensure_agent_accepting_chats_column()
    ensure_tenant_agent_management_columns()
    ensure_message_enhancements()
    ensure_dm_team_message_metadata_json()
    ensure_trending_product_image_arrays()
    ensure_trending_product_unit_pieces_column()
    ensure_trending_product_is_trending_column()
    ensure_whatsapp_broadcast_tables()
    ensure_user_emails_lowercased()
    ensure_pgvector_extension()
    ensure_admin_user()
    hydrate_openai_api_key_from_db()
    if bool(getattr(settings, "conversation_memory_enabled", True)) and bool(
        getattr(settings, "memory_stats_log_enabled", True)
    ):
        intv = int(getattr(settings, "memory_stats_log_interval_seconds", 86400) or 0)
        if intv > 0:
            memory_stats_task = asyncio.create_task(_memory_stats_background_loop())
    broadcast_agent_task = asyncio.create_task(_broadcast_agent_enforcement_loop())
    stale_chat_task: Optional[asyncio.Task] = asyncio.create_task(_stale_chat_release_loop())
    yield
    # Shutdown
    if broadcast_agent_task is not None:
        broadcast_agent_task.cancel()
        try:
            await broadcast_agent_task
        except asyncio.CancelledError:
            pass
    if stale_chat_task is not None:
        stale_chat_task.cancel()
        try:
            await stale_chat_task
        except asyncio.CancelledError:
            pass
    if memory_stats_task is not None:
        memory_stats_task.cancel()
        try:
            await memory_stats_task
        except asyncio.CancelledError:
            pass


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
        settings.frontend_base_url,
    ],
    # Accept Vercel preview deployments and custom Vercel aliases.
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Cache CORS preflight responses in browsers to reduce OPTIONS volume.
    max_age=86400,
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
app.include_router(wa_templates_router, prefix="/api/broadcasts", tags=["broadcasts"])
app.include_router(broadcast_campaigns_router, prefix="/api/broadcasts", tags=["broadcasts"])
app.include_router(admin_realtime_router, prefix="/api/admin-realtime", tags=["admin-realtime"])
app.include_router(knowledge_router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(internal_dm_router, prefix="/api/internal-dm", tags=["internal-dm"])
app.include_router(agent_portal_router, prefix="/api/agent-portal", tags=["agent-portal"])
app.include_router(orders_export_router, prefix="/api/orders", tags=["orders"])
app.include_router(invoices_export_router, prefix="/api/invoices", tags=["invoices"])
app.include_router(upload_router, prefix="/api/upload", tags=["upload"])
app.include_router(trending_products_admin_router)
app.include_router(trending_public_router)
app.include_router(trending_page_router)


@app.get("/")
async def root():
    return {"message": "Arabia Dropshipping API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@app.get("/api/health/memory")
async def memory_health() -> Dict[str, Any]:
    """
    Redis / Valkey memory layer status for ops dashboards.
    Does not expose secrets; safe to expose behind your normal API auth / network rules.
    """
    from services.memory_service import ConversationMemory, _get_redis

    ok = ConversationMemory.health_check()
    out: Dict[str, Any] = {"redis_ok": ok, "status": "ok" if ok else "degraded"}
    r = _get_redis()
    if r:
        try:
            mem_info = r.info("memory")
            out["used_memory_human"] = mem_info.get("used_memory_human")
            out["used_memory_peak_human"] = mem_info.get("used_memory_peak_human")
            out["keyspace"] = r.info("keyspace") or {}
        except Exception as exc:  # noqa: BLE001
            out["error"] = str(exc)
    return out


@app.get("/admin/test-dashboard")
async def test_dashboard():
    """Static checklist + live memory health (same-origin fetch to /api/health/memory)."""
    path = _TEMPLATES_DIR / "test_dashboard.html"
    if not path.is_file():
        return {"error": "test_dashboard.html not found", "path": str(path)}
    return FileResponse(path)
