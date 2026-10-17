"""Command api is the HTTP entrypoint for the credit-cabinet backend."""

from __future__ import annotations

import logging

import uvicorn

from .config import load
from .logging import configure
from .platform import ai, db
from .server import create_app

log = logging.getLogger("app.main")


def run() -> None:
    cfg = load()
    configure(cfg.app_env)

    pool = db.open_db(cfg)
    db.auto_migrate(pool)

    app = create_app(cfg, pool, ai.new(cfg))
    host, port = cfg.addr
    log.info("server starting", extra={"addr": cfg.http_addr, "env": cfg.app_env})

    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)


def main() -> None:
    try:
        run()
    except Exception as exc:
        logging.getLogger("app.main").error("fatal", extra={"err": str(exc)})
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
