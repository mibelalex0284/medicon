from typing import Any, List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


import urllib.parse
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def normalize_database_url(url: str) -> str:
    """
    Normalizes database URLs to ensure a consistent driver strategy.

    For PostgreSQL connections, maps schemes (postgres, postgresql,
    postgresql+psycopg, postgresql+asyncpg) to postgresql+psycopg2 to ensure the
    synchronous SQLAlchemy engine and Alembic migrations consistently use the
    installed psycopg2 driver. Preserves SQLite and non-PostgreSQL URLs.
    """
    if not url:
        return url
    url_stripped = url.strip()
    if url_stripped.startswith("sqlite"):
        return url_stripped

    parts = urllib.parse.urlsplit(url_stripped)
    scheme = parts.scheme.lower()
    if scheme in ("postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2", "postgresql+asyncpg"):
        return urllib.parse.urlunsplit(("postgresql+psycopg2", parts.netloc, parts.path, parts.query, parts.fragment))
    return url_stripped


class Settings(BaseSettings):
    # Application & Environment
    PROJECT_NAME: str = "CareRoute-X API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # CORS & Web Client
    FRONTEND_URL: str = "http://localhost:3000"
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return list(v)
        return []

    # Supabase Configuration
    SUPABASE_URL: str = "https://rkyrzctczohppspnzfxp.supabase.co"
    SUPABASE_ANON_KEY: str = "your-anon-key"
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = None
    SUPABASE_JWT_ALGORITHM: str = "ES256"
    SUPABASE_JWKS_URL: Optional[str] = "https://rkyrzctczohppspnzfxp.supabase.co/auth/v1/.well-known/jwks.json"
    SUPABASE_JWT_AUDIENCE: Optional[str] = None

    @field_validator("SUPABASE_JWT_SECRET", mode="before")
    @classmethod
    def assemble_jwt_secret(cls, v: Any) -> Optional[str]:
        if isinstance(v, str):
            v_stripped = v.strip()
            return v_stripped if v_stripped else None
        return v

    @property
    def is_supabase_configured(self) -> bool:
        """Determines if valid non-placeholder Supabase configuration is present."""
        if not self.SUPABASE_URL or "your-project" in self.SUPABASE_URL or "placeholder" in self.SUPABASE_URL:
            return False
        if not self.SUPABASE_ANON_KEY or "your-anon-key" in self.SUPABASE_ANON_KEY or "placeholder" in self.SUPABASE_ANON_KEY:
            return False
        return True

    @property
    def is_jwks_configured(self) -> bool:
        """Determines if valid non-placeholder JWKS configuration is present."""
        url = self.effective_jwks_url
        if not url:
            return False
        if "your-project" in url or "placeholder" in url:
            return False
        return True

    @property
    def effective_jwks_url(self) -> Optional[str]:
        """Resolves the live JWKS URL for asymmetric ES256 verification."""
        if self.SUPABASE_JWKS_URL and "placeholder" not in self.SUPABASE_JWKS_URL and "your-project" not in self.SUPABASE_JWKS_URL:
            return self.SUPABASE_JWKS_URL
        if self.SUPABASE_URL and "placeholder" not in self.SUPABASE_URL and "your-project" not in self.SUPABASE_URL:
            return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None

    def validate_production_configuration(self) -> None:
        """Enforces that production builds fail immediately if authentication secrets or signing configs are invalid."""
        if self.ENVIRONMENT.lower() == "production":
            if not self.is_supabase_configured:
                raise RuntimeError(
                    "FATAL: Production environment requires authentic Supabase configuration. "
                    "SUPABASE_URL and SUPABASE_ANON_KEY cannot be placeholders."
                )

            alg = self.SUPABASE_JWT_ALGORITHM.upper()
            if alg.startswith("HS"):
                # Symmetric HS256 genuinely requires SUPABASE_JWT_SECRET
                if not self.SUPABASE_JWT_SECRET:
                    raise RuntimeError(
                        f"FATAL: Production environment requires authentic SUPABASE_JWT_SECRET "
                        f"when configured for {alg} verification."
                    )
                if "placeholder" in self.SUPABASE_JWT_SECRET:
                    raise RuntimeError(
                        "FATAL: Production environment cannot use placeholder SUPABASE_JWT_SECRET."
                    )
            elif alg.startswith("ES") or alg.startswith("RS"):
                # Asymmetric ES256/RS256 requires authentic JWKS configuration
                if not self.is_jwks_configured:
                    raise RuntimeError(
                        f"FATAL: Production environment requires authentic JWKS configuration "
                        f"for {alg} verification. Set SUPABASE_JWKS_URL or valid SUPABASE_URL."
                    )
                # If a secret is optionally provided for legacy symmetric tokens, ensure it is not a placeholder
                if self.SUPABASE_JWT_SECRET and "placeholder" in self.SUPABASE_JWT_SECRET:
                    raise RuntimeError(
                        "FATAL: Production environment cannot use placeholder SUPABASE_JWT_SECRET."
                    )
            else:
                raise RuntimeError(
                    f"FATAL: Unsupported SUPABASE_JWT_ALGORITHM in production: '{alg}'."
                )

    # Database
    DATABASE_URL: str = "sqlite:///./careroute.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_database_url(cls, v: Any) -> str:
        if isinstance(v, str):
            return normalize_database_url(v)
        return v

    # Gemini & Stage 4B Triage Configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.6-flash"
    DDXPLUS_DATA_PATH: Optional[str] = None
    TRIAGE_MAX_TURNS: int = 7
    TRIAGE_MIN_COMPLETENESS: float = 0.70

    model_config = SettingsConfigDict(
        env_file=[str(BACKEND_DIR / ".env"), ".env"],
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )



settings = Settings()
