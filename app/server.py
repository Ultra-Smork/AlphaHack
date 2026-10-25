"""Wire configuration, dependencies, middleware, and routes into a FastAPI app."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import responses
from .auth import TokenManager
from .config import Config
from .handler.applications import router as applications_router
from .handler.auth import new_auth_router
from .handler.health import new_health_router
from .middleware import cors
from .middleware.logger import LoggerMiddleware
from .middleware.recovery import RecoveryMiddleware
from .middleware.requestid import RequestIDMiddleware
from .platform import db
from .platform.ai.ml_client import get_ml_client
from .platform.seed import seed

log = logging.getLogger("app.server")


def create_app(cfg: Config, database: db.Database) -> FastAPI:
    """Assemble the app and its dependency graph."""
    tokens = TokenManager(cfg.jwt.secret, cfg.jwt.ttl)
    ml_client = get_ml_client(cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            db.assert_schema_compatible(database.engine)
            try:
                with database.session_factory() as session:
                    seed(session)
            except Exception as exc:
                log.error("demo seed failed", extra={"err": str(exc)})
                raise
            yield
        finally:
            database.close()

    app = FastAPI(title="Суирники3", lifespan=lifespan)

    app.state.config = cfg
    app.state.database = database
    app.state.session_factory = database.session_factory
    app.state.tokens = tokens
    app.state.ml_client = ml_client

    responses.install_error_handlers(app)

    # Added inner-to-outer, so the outermost is RequestID.
    cors_class, cors_kwargs = cors.cors()
    cors_kwargs["allow_origins"] = cfg.cors_origin_list
    app.add_middleware(cors_class, **cors_kwargs)
    app.add_middleware(RecoveryMiddleware)
    app.add_middleware(LoggerMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(new_health_router(database.engine))

    api = APIRouter(prefix="/api")
    api.include_router(new_auth_router(tokens))
    api.include_router(applications_router)
    app.include_router(api)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/", include_in_schema=False)
        def spa_root() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path in {"api", "docs", "redoc", "openapi.json"} or full_path.startswith(
                "api/"
            ):
                raise HTTPException(status_code=404)

            candidate = (static_dir / full_path).resolve()
            if (
                full_path
                and candidate.is_file()
                and candidate.is_relative_to(static_dir.resolve())
            ):
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app
