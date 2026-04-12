from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    
    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # Cloudflare R2 (S3-compatible). Optional; enables presigned uploads and inbox media.
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket_name: Optional[str] = None
    r2_presign_put_seconds: int = 60
    r2_presign_get_seconds: int = 3600
    
    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # LLM
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.2
    
    # WhatsApp
    wati_api_key: Optional[str] = None
    wati_api_url: str = "https://api.wati.io"
    meta_whatsapp_access_token: Optional[str] = None
    meta_whatsapp_verify_token: Optional[str] = None
    meta_whatsapp_phone_number_id: Optional[str] = None
    meta_whatsapp_waba_id: Optional[str] = None
    meta_graph_api_version: str = "v21.0"
    
    # Optional: merchant store HTTP API (for AI context / order lookups)
    client_api_base_url: Optional[str] = None
    client_api_key: Optional[str] = None
    client_api_bearer_token: Optional[str] = None

    # Customer bot: auto-clear scripted flow after N days with no customer message. Default 7;
    # set CUSTOMER_BOT_INACTIVITY_RESET_DAYS=0 to disable.
    customer_bot_inactivity_reset_days: int = 7

    # Application
    environment: str = "development"
    debug: bool = True
    frontend_base_url: str = "http://localhost:3000"
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None

    # Gmail (or other) SMTP for password reset and transactional mail
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# Runtime override for OpenAI API key (set via admin Settings UI). Takes precedence over env.
_openai_api_key_override: Optional[str] = None


def get_openai_api_key() -> Optional[str]:
    # Environment key wins over a runtime/DB override so hosting dashboards (e.g. Render) stay canonical.
    env_key = (settings.openai_api_key or "").strip()
    if env_key:
        return env_key
    override = (_openai_api_key_override or "").strip()
    return override or None


def set_openai_api_key_override(key: Optional[str]) -> None:
    global _openai_api_key_override
    _openai_api_key_override = key


def hydrate_openai_api_key_from_db() -> None:
    """
    If OPENAI_API_KEY is not set in the environment, load a tenant-stored key from the DB.
    When the host (e.g. Render) provides OPENAI_API_KEY, that value is always used — the DB
    is not applied on startup so dashboard env vars stay authoritative.
    """
    env_key = (settings.openai_api_key or "").strip()
    if env_key:
        return
    try:
        from database import SessionLocal
        from models import Tenant

        db = SessionLocal()
        try:
            for t in db.query(Tenant).order_by(Tenant.id.asc()).all():
                raw = getattr(t, "openai_api_key", None)
                if raw and str(raw).strip():
                    set_openai_api_key_override(str(raw).strip())
                    return
        finally:
            db.close()
    except Exception:
        pass
