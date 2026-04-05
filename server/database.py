from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

# Connection uses pool_pre_ping for reliability; pool size uses SQLAlchemy defaults (fast).
# Set DATABASE_URL in .env e.g. postgresql://user:password@localhost:5432/arabia
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_broadcast_delivery_columns() -> None:
    """
    Add broadcast delivery columns on existing PostgreSQL DBs (no Alembic in this repo).
    """
    try:
        insp = inspect(engine)
        if "broadcasts" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("broadcasts")}
    except Exception:
        return
    stmts: list[str] = []
    if "target_ai" not in cols:
        stmts.append(
            "ALTER TABLE broadcasts ADD COLUMN target_ai BOOLEAN NOT NULL DEFAULT true"
        )
    if "delivery_notify_agents" not in cols:
        stmts.append(
            "ALTER TABLE broadcasts ADD COLUMN delivery_notify_agents BOOLEAN NOT NULL DEFAULT false"
        )
    if "delivery_notify_customers_whatsapp" not in cols:
        stmts.append(
            "ALTER TABLE broadcasts ADD COLUMN delivery_notify_customers_whatsapp BOOLEAN NOT NULL DEFAULT false"
        )
    if not stmts:
        return
    try:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception:
        pass


def ensure_team_channel_admin_sender_columns() -> None:
    """
    Allow admin-originated team channel messages (nullable sender_agent_id, posted_by_admin).
    """
    try:
        insp = inspect(engine)
        if "team_channel_messages" not in insp.get_table_names():
            return
        col_list = insp.get_columns("team_channel_messages")
        cols = {c["name"] for c in col_list}
        sender_nullable = next(
            (c.get("nullable", True) for c in col_list if c["name"] == "sender_agent_id"),
            True,
        )
    except Exception:
        return
    try:
        with engine.begin() as conn:
            if "posted_by_admin" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE team_channel_messages ADD COLUMN posted_by_admin "
                        "BOOLEAN NOT NULL DEFAULT false"
                    )
                )
            if not sender_nullable:
                conn.execute(
                    text(
                        "ALTER TABLE team_channel_messages ALTER COLUMN sender_agent_id DROP NOT NULL"
                    )
                )
    except Exception:
        pass


def ensure_team_channel_read_states_table() -> None:
    """Create team_channel_member_read_states if missing (no Alembic)."""
    try:
        insp = inspect(engine)
        names = insp.get_table_names()
        if "team_channel_member_read_states" in names:
            return
    except Exception:
        return
    try:
        from models import TeamChannelMemberReadState  # noqa: WPS433

        TeamChannelMemberReadState.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass


def ensure_agent_read_state_tables() -> None:
    """Create conversation_agent_read_states and internal_dm_member_read_states if missing."""
    try:
        from models import ConversationAgentReadState, InternalDmMemberReadState  # noqa: WPS433

        ConversationAgentReadState.__table__.create(bind=engine, checkfirst=True)
        InternalDmMemberReadState.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass


def ensure_user_avatar_url_column() -> None:
    try:
        insp = inspect(engine)
        if "users" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("users")}
    except Exception:
        return
    if "avatar_url" in cols:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url TEXT"))
    except Exception:
        pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
