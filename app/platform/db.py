"""Open the Postgres connection pool."""

from __future__ import annotations

from psycopg_pool import ConnectionPool

from ..config import Config

# Pool limits, mirroring the Go settings.
_MAX_OPEN = 25
_MAX_IDLE_SECONDS = 5 * 60
_MAX_LIFETIME_SECONDS = 30 * 60


def open_db(cfg: Config) -> ConnectionPool:
    """Create the pool. It does not require the database to be up: connections
    are opened on demand (min_size=0), so the process can boot and report via
    /readyz.
    """
    return ConnectionPool(
        conninfo=cfg.database.url,
        min_size=0,
        max_size=_MAX_OPEN,
        max_idle=_MAX_IDLE_SECONDS,
        max_lifetime=_MAX_LIFETIME_SECONDS,
        kwargs={"connect_timeout": 2},
        open=True,
        name="alphahack",
    )


def ping(pool: ConnectionPool, timeout: float) -> None:
    """Raise if the database is unreachable within timeout seconds."""
    with pool.connection(timeout=timeout) as conn:
        conn.execute("SELECT 1")


def auto_migrate(_pool: ConnectionPool) -> None:
    """Register domain models. Empty until models exist.

    Prefer versioned SQL in migrations/ for anything shipped beyond local
    development.
    """
