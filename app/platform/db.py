"""SQLAlchemy engine, session factory, and request-scoped sessions."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ..config import Config
from ..models import Base

_CONNECT_TIMEOUT_SECONDS = 5


class Database:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        if parsed.get_backend_name() != "sqlite":
            raise ValueError(f"db: only sqlite URLs are supported, got {url!r}")

        engine_kwargs: dict[str, object] = {
            "connect_args": {
                "check_same_thread": False,
                "timeout": _CONNECT_TIMEOUT_SECONDS,
            },
            "pool_pre_ping": True,
        }
        if parsed.database in {None, "", ":memory:"}:
            engine_kwargs["poolclass"] = StaticPool

        self.engine = create_engine(url, **engine_kwargs)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

        is_memory = parsed.database in {None, "", ":memory:"}

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA busy_timeout = 5000")
            if not is_memory:
                cursor.execute("PRAGMA journal_mode = WAL")
            cursor.close()

    def close(self) -> None:
        self.engine.dispose()


def open_db(cfg: Config) -> Database:
    return Database(cfg.database.url)


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def assert_schema_compatible(engine: Engine) -> None:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    problems: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        expected = {column.name for column in table.columns}
        missing = sorted(expected - actual)
        if missing:
            problems.append(f"{table.name}: missing {', '.join(missing)}")

    if problems:
        raise RuntimeError(
            "db: incompatible schema detected. "
            "Run `make reset-db` once. Details: " + "; ".join(problems)
        )


def auto_migrate(engine: Engine, drop_on_start: bool = False) -> None:
    if drop_on_start:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            for table in inspect(conn).get_table_names():
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
            conn.execute(text("PRAGMA foreign_keys = ON"))
    else:
        assert_schema_compatible(engine)

    Base.metadata.create_all(engine)
    assert_schema_compatible(engine)


def ping(engine: Engine, timeout: float) -> None:
    del timeout
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
