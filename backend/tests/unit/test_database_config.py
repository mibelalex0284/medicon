"""
Unit tests for database URL normalization and driver configuration.
Verifies consistent psycopg2 driver selection across URL schemes without requiring production credentials.
"""

import pytest
from sqlalchemy import create_engine
from app.core.config import Settings, normalize_database_url


class TestDatabaseUrlNormalization:
    """Tests URL scheme mapping for synchronous SQLAlchemy and Alembic."""

    @pytest.mark.parametrize(
        "input_url, expected_url",
        [
            (
                "postgres://user:pass@test-host:5432/testdb",
                "postgresql+psycopg2://user:pass@test-host:5432/testdb",
            ),
            (
                "postgresql://user:pass@test-host:5432/testdb",
                "postgresql+psycopg2://user:pass@test-host:5432/testdb",
            ),
            (
                "postgresql+psycopg://user:pass@test-host:5432/testdb",
                "postgresql+psycopg2://user:pass@test-host:5432/testdb",
            ),
            (
                "postgresql+psycopg2://user:pass@test-host:5432/testdb",
                "postgresql+psycopg2://user:pass@test-host:5432/testdb",
            ),
            (
                "postgresql+asyncpg://user:pass@test-host:5432/testdb",
                "postgresql+psycopg2://user:pass@test-host:5432/testdb",
            ),
            (
                "POSTGRESQL://user:pass@test-host:5432/testdb",
                "postgresql+psycopg2://user:pass@test-host:5432/testdb",
            ),
            (
                "sqlite:///./careroute.db",
                "sqlite:///./careroute.db",
            ),
            (
                "sqlite:///:memory:",
                "sqlite:///:memory:",
            ),
        ],
    )
    def test_normalize_database_url_schemes(self, input_url: str, expected_url: str) -> None:
        assert normalize_database_url(input_url) == expected_url

    def test_preserves_query_parameters_and_credentials(self) -> None:
        url = "postgresql+psycopg://test.user:p%40ss_word@aws-0-test.pooler.supabase.com:5432/postgres?sslmode=require&connect_timeout=10"
        normalized = normalize_database_url(url)
        assert normalized.startswith("postgresql+psycopg2://")
        assert "test.user:p%40ss_word@aws-0-test.pooler.supabase.com:5432/postgres" in normalized
        assert "sslmode=require" in normalized
        assert "connect_timeout=10" in normalized

    def test_empty_and_whitespace_urls(self) -> None:
        assert normalize_database_url("") == ""
        assert normalize_database_url(None) is None  # type: ignore[arg-type]

    def test_settings_field_validator_normalizes_url(self) -> None:
        """Verifies that Pydantic Settings applies the database URL normalization on instantiation."""
        custom_settings = Settings(
            DATABASE_URL="postgresql+psycopg://test_user:test_pass@localhost:5432/test_db",
            ENVIRONMENT="test",
        )
        assert custom_settings.DATABASE_URL == "postgresql+psycopg2://test_user:test_pass@localhost:5432/test_db"

    def test_sqlalchemy_engine_dialect_resolution(self) -> None:
        """Verifies that create_engine with normalized URL binds to psycopg2 without raising ModuleNotFoundError."""
        raw_psycopg3_url = "postgresql+psycopg://dummy:dummy@localhost:5432/dummy"
        normalized_url = normalize_database_url(raw_psycopg3_url)

        engine = create_engine(normalized_url)
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg2"
        # Confirm that the DBAPI module is importable and is psycopg2
        assert engine.dialect.dbapi.__name__ == "psycopg2"
        engine.dispose()
