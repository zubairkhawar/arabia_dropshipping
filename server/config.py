from pydantic import model_validator
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
    # Optional public base for R2 (e.g. https://pub-xxxxx.r2.dev or custom domain). Used for stored image URLs.
    r2_public_base_url: Optional[str] = None
    r2_public_url: Optional[str] = None  # alias — merged into r2_public_base_url below
    
    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # LLM
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.2
    kb_min_score: int = 1
    kb_use_embeddings: bool = False
    # When True, the LangChain system prompt asks the model for 3 contextual follow-up suggestions per turn.
    llm_followup_suggestions: bool = True
    
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

    # Customer bot: route the trending / non-trending product flow through the LLM-driven
    # runner instead of the deterministic state machine. "off" keeps legacy logic;
    # "shadow" runs the LLM in parallel (logs only, deterministic reply wins); "on" uses the
    # LLM reply and falls back to deterministic only on failure.
    trending_llm_mode: str = "on"
    # Optional comma-separated allowlist of customer phones that opt into the LLM
    # trending flow regardless of ``trending_llm_mode``. Leave empty to apply the mode to all.
    trending_llm_allowlist: str = ""

    # Customer bot: script verification (email/mobile) expires after N days. Default 3;
    # set CUSTOMER_BOT_VERIFICATION_EXPIRY_DAYS=0 to disable auto-expiry.
    customer_bot_verification_expiry_days: int = 3

    # Customer bot: temporarily bypass the email OTP step. When True, the existing-
    # customer flow jumps straight from email → mobile, and identity is proven purely
    # by a matching (email, mobile) pair in get_customer_by_email_mobile_first_hit.
    # Leave False in production; flip to True (CUSTOMER_BOT_SKIP_EMAIL_OTP=true) only
    # while debugging the store-API customer lookup end-to-end.
    customer_bot_skip_email_otp: bool = False

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

    @model_validator(mode="after")
    def _merge_r2_public_url(self) -> "Settings":
        """Accept R2_PUBLIC_URL as an alias for R2_PUBLIC_BASE_URL."""
        if not self.r2_public_base_url and self.r2_public_url:
            self.r2_public_base_url = self.r2_public_url
        return self

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
