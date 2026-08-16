"""Tests for DatabaseSettings DATABASE_URL support."""

import pytest

from aegra_api.settings import AppSettings, DatabaseSettings


class TestDatabaseURLSupport:
    """Test that DATABASE_URL is used directly for computed URLs."""

    def test_defaults_when_no_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Individual defaults are used when DATABASE_URL is not set."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        monkeypatch.delenv("POSTGRES_PORT", raising=False)
        monkeypatch.delenv("POSTGRES_DB", raising=False)
        monkeypatch.delenv("POSTGRES_SSLMODE", raising=False)

        db = DatabaseSettings(_env_file=None)

        assert db.POSTGRES_USER == "postgres"
        assert db.POSTGRES_HOST == "localhost"
        assert db.POSTGRES_PORT == "5433"
        assert db.POSTGRES_DB == "aegra"
        assert db.POSTGRES_SSLMODE == "require"
        assert "postgres:postgres@localhost:5433/aegra" in db.database_url
        assert db.database_url.endswith("?ssl=require")
        assert db.database_url_sync.endswith("?sslmode=require")

    def test_database_url_used_directly_in_computed_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DATABASE_URL is used directly with correct driver prefix."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://rdsuser:rdspass@rds.aws.com:5432/prod")

        db = DatabaseSettings(_env_file=None)

        assert db.database_url == "postgresql+asyncpg://rdsuser:rdspass@rds.aws.com:5432/prod"
        assert db.database_url_sync == "postgresql://rdsuser:rdspass@rds.aws.com:5432/prod"

    def test_query_params_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SSL and other query params from DATABASE_URL are preserved."""
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://user:pass@host:5432/db?sslmode=require&connect_timeout=10",
        )

        db = DatabaseSettings(_env_file=None)

        assert "sslmode=require" in db.database_url
        assert "connect_timeout=10" in db.database_url
        assert "sslmode=require" in db.database_url_sync
        assert db.database_url.startswith("postgresql+asyncpg://")
        assert db.database_url_sync.startswith("postgresql://")

    def test_driver_prefix_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Driver prefix is always normalized regardless of input."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@host:5432/db")

        db = DatabaseSettings(_env_file=None)

        assert db.database_url.startswith("postgresql+asyncpg://")
        assert db.database_url_sync.startswith("postgresql://")
        assert not db.database_url_sync.startswith("postgresql+")

    def test_legacy_postgres_scheme_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Legacy postgres:// scheme (Heroku/Render) is normalized."""
        monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/db")

        db = DatabaseSettings(_env_file=None)

        assert db.database_url.startswith("postgresql+asyncpg://")
        assert db.database_url_sync.startswith("postgresql://")
        assert "user:pass@host:5432/db" in db.database_url

    def test_individual_vars_still_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Individual POSTGRES_* vars work when DATABASE_URL is not set."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("POSTGRES_USER", "custom_user")
        monkeypatch.setenv("POSTGRES_PASSWORD", "custom_pass")
        monkeypatch.setenv("POSTGRES_HOST", "custom-host")
        monkeypatch.setenv("POSTGRES_PORT", "5555")
        monkeypatch.setenv("POSTGRES_DB", "custom_db")

        db = DatabaseSettings(_env_file=None)

        assert db.POSTGRES_USER == "custom_user"
        assert "custom_user:custom_pass@custom-host:5555/custom_db" in db.database_url

    def test_malformed_database_url_does_not_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Malformed DATABASE_URL doesn't crash — regex just won't match."""
        monkeypatch.setenv("DATABASE_URL", "not-a-url")

        db = DatabaseSettings(_env_file=None)

        # _normalize_scheme won't match, so URL passes through as-is
        assert db.DATABASE_URL == "not-a-url"

    def test_blank_postgres_sslmode_omits_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("POSTGRES_SSLMODE", "")

        db = DatabaseSettings(_env_file=None)

        assert not db.POSTGRES_SSLMODE
        assert "?" not in db.database_url
        assert "?" not in db.database_url_sync


class TestAppSettingsDefaults:
    def test_in_cluster_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in ("HOST", "PORT", "AUTH_TYPE", "AEGRA_CONFIG", "NEO4J_MCP_HOST"):
            monkeypatch.delenv(key, raising=False)

        app = AppSettings(_env_file=None)

        assert app.HOST == "0.0.0.0"
        assert app.PORT == 8000
        assert app.AUTH_TYPE == "noop"
        assert app.AEGRA_CONFIG == "aegra.json"
        assert app.NEO4J_MCP_HOST == "http://neo4j-mcp.neo4j.svc.cluster.local:8811"
