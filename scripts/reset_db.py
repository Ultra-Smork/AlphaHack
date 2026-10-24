"""Drop the configured SQLite schema, recreate it, and seed demo data."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load
from app.platform import db
from app.platform.seed import seed


def main() -> None:
    cfg = load()
    database = db.open_db(cfg)
    try:
        db.auto_migrate(database.engine, drop_on_start=True)
        with database.session_factory() as session:
            seed(session)
    finally:
        database.close()

    print(f"database reset: {cfg.database.url}")


if __name__ == "__main__":
    main()
