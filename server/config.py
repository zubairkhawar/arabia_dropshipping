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
    
    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # LLM
    openai_api_key: Optional[str] = None
    
    # WhatsApp
    wati_api_key: Optional[str] = None
    wati_api_url: str = "https://api.wati.io"
    
    # Application
    environment: str = "development"
    debug: bool = True
    frontend_base_url: str = "http://localhost:3000"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# Runtime override for OpenAI API key (set via admin Settings UI). Takes precedence over env.
_openai_api_key_override: Optional[str] = None


def get_openai_api_key() -> Optional[str]:
    return _openai_api_key_override or settings.openai_api_key


def set_openai_api_key_override(key: Optional[str]) -> None:
    global _openai_api_key_override
    _openai_api_key_override = key
