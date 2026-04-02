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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
