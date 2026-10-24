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
    SUPABASE_URL: str = "https://rkyrzctczohppspnzfxp.supabase.co"
    SUPABASE_ANON_KEY: str = "your-anon-key"
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = "your-supabase-jwt-secret-placeholder-for-dev"
    SUPABASE_JWT_ALGORITHM: str = "ES256"
    SUPABASE_JWKS_URL: Optional[str] = "https://rkyrzctczohppspnzfxp.supabase.co/auth/v1/.well-known/jwks.json"

    @property
    def is_supabase_configured(self) -> bool:
        """Determines if valid non-placeholder Supabase configuration is present."""
        if not self.SUPABASE_URL or "your-project" in self.SUPABASE_URL or "placeholder" in self.SUPABASE_URL:
            return False
        if not self.SUPABASE_ANON_KEY or "your-anon-key" in self.SUPABASE_ANON_KEY or "placeholder" in self.SUPABASE_ANON_KEY:
            return False
        return True

    @property
    def effective_jwks_url(self) -> Optional[str]:
        """Resolves the live JWKS URL for asymmetric ES256 verification."""
        if self.SUPABASE_JWKS_URL:
            return self.SUPABASE_JWKS_URL
        if self.SUPABASE_URL and "placeholder" not in self.SUPABASE_URL and "your-project" not in self.SUPABASE_URL:
            return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None

    def validate_production_configuration(self) -> None:
        """Enforces that production builds fail immediately if authentication secrets are missing or placeholder."""
        if self.ENVIRONMENT.lower() == "production":
            if not self.is_supabase_configured:
                raise RuntimeError(
                    "FATAL: Production environment requires authentic Supabase configuration. "
                    "SUPABASE_URL and SUPABASE_ANON_KEY cannot be placeholders."
                )
            if self.SUPABASE_JWT_SECRET and "placeholder" in self.SUPABASE_JWT_SECRET:
                raise RuntimeError(
                    "FATAL: Production environment cannot use placeholder SUPABASE_JWT_SECRET."
                )

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
