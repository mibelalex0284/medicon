from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # Application & Environment
    PROJECT_NAME: str = "CareRoute-X API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Supabase Configuration
    SUPABASE_URL: str = "https://your-project.supabase.co"
    SUPABASE_ANON_KEY: str = "your-anon-key"
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: str = "your-supabase-jwt-secret-placeholder-for-dev"
    SUPABASE_JWT_ALGORITHM: str = "HS256"

    # Database
    DATABASE_URL: str = "sqlite:///./careroute.db"

    # Gemini & Stage 4B Triage Configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.6-flash"
    DDXPLUS_DATA_PATH: str = "D:\\22687585.zip"
    TRIAGE_MAX_TURNS: int = 7
    TRIAGE_MIN_COMPLETENESS: float = 0.70

    model_config = SettingsConfigDict(
        env_file=[str(BACKEND_DIR / ".env"), ".env"],
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )



settings = Settings()
