#!/usr/bin/env python3
"""
Drop all SQLAlchemy-managed tables and recreate an empty schema, then run the same
best-effort ALTER/CREATE helpers as FastAPI startup and re-seed default tenant + admin.

Usage (from repo root or from server/):

  cd server
  CONFIRM_RESET=1 python scripts/reset_database.py

Remote / hosted Postgres (not localhost):

  CONFIRM_RESET=1 ALLOW_REMOTE_DB_RESET=1 python scripts/reset_database.py

Loads server/.env when python-dotenv is installed (same as the app).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))
os.chdir(SERVER_ROOT)


def _looks_local_database_url(url: str) -> bool:
    u = (url or "").lower()
    return "localhost" in u or "127.0.0.1" in u or "0.0.0.0" in u


def _ensure_admin_user() -> None:
    from config import settings
    from database import Base, engine, SessionLocal
    from models import Tenant, User
    from services.auth_service.services import get_password_hash

    if not settings.admin_email or not settings.admin_password:
        print("ADMIN_EMAIL / ADMIN_PASSWORD not set — skipping admin seed.")
        return

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

        admin_email_norm = (settings.admin_email or "").strip().lower()
        existing = db.query(User).filter(User.email == admin_email_norm).first()
        if existing:
            print(f"Admin user already exists: {admin_email_norm}")
            return

        user = User(
            tenant_id=tenant.id,
            email=admin_email_norm,
            full_name="Arabia Admin",
            role="admin",
            hashed_password=get_password_hash(settings.admin_password),
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        print(f"Created admin user: {settings.admin_email}")
    finally:
        db.close()


def main() -> int:
    if os.environ.get("CONFIRM_RESET", "").strip() != "1":
        print("Refusing: set CONFIRM_RESET=1 to wipe the database.")
        return 1

    try:
        from dotenv import load_dotenv

        load_dotenv(SERVER_ROOT / ".env")
    except ImportError:
        pass

    import models  # noqa: F401 — register all tables on Base

    from config import hydrate_openai_api_key_from_db, settings
    from database import (
        Base,
        engine,
        ensure_agent_read_state_tables,
        ensure_broadcast_delivery_columns,
        ensure_broadcast_whatsapp_template_columns,
        ensure_dm_team_message_metadata_json,
        ensure_message_enhancements,
        ensure_pgvector_extension,
        ensure_team_channel_admin_sender_columns,
        ensure_team_channel_read_states_table,
        ensure_tenant_agent_management_columns,
        ensure_tenant_display_timezone_column,
        ensure_tenant_openai_api_key_column,
        ensure_user_avatar_url_column,
    )

    db_url = settings.database_url or ""
    if not _looks_local_database_url(db_url):
        if os.environ.get("ALLOW_REMOTE_DB_RESET", "").strip() != "1":
            print(
                "Refusing: DATABASE_URL does not look local.\n"
                "If you really intend to wipe this database, set ALLOW_REMOTE_DB_RESET=1 "
                "in addition to CONFIRM_RESET=1."
            )
            return 1

    print("Dropping all ORM tables …")
    Base.metadata.drop_all(bind=engine)
    print("Creating tables …")
    Base.metadata.create_all(bind=engine)

    print("Running startup schema ensures …")
    ensure_broadcast_delivery_columns()
    ensure_broadcast_whatsapp_template_columns()
    ensure_team_channel_admin_sender_columns()
    ensure_team_channel_read_states_table()
    ensure_agent_read_state_tables()
    ensure_tenant_display_timezone_column()
    ensure_tenant_openai_api_key_column()
    ensure_user_avatar_url_column()
    ensure_tenant_agent_management_columns()
    ensure_message_enhancements()
    ensure_dm_team_message_metadata_json()
    ensure_pgvector_extension()

    _ensure_admin_user()
    hydrate_openai_api_key_from_db()
    print("Database reset complete. Restart the API if it is already running.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
