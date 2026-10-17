"""Wire configuration, dependencies, middleware, and routes into a FastAPI app."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from psycopg_pool import ConnectionPool

from . import responses
from .auth import TokenManager
from .config import Config
from .handler.auth import new_auth_router
from .handler.health import new_health_router
from .middleware import cors
from .middleware.auth import get_user_id
from .middleware.logger import LoggerMiddleware
from .middleware.recovery import RecoveryMiddleware
from .middleware.requestid import RequestIDMiddleware
from .platform.ai import Client


def create_app(cfg: Config, pool: ConnectionPool, assistant: Client) -> FastAPI:
    """Assemble the app and its dependency graph."""
    tokens = TokenManager(cfg.jwt.secret, cfg.jwt.ttl)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        pool.close()

    app = FastAPI(title="credit-cabinet", lifespan=lifespan)

    app.state.config = cfg
    app.state.pool = pool
    app.state.tokens = tokens
    app.state.assistant = assistant

    responses.install_error_handlers(app)

    # Added inner-to-outer, so the outermost is RequestID.
    cors_class, cors_kwargs = cors.cors()
    app.add_middleware(cors_class, **cors_kwargs)
    app.add_middleware(RecoveryMiddleware)
    app.add_middleware(LoggerMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(new_health_router(pool))

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(new_auth_router(tokens))

    # Authenticated routes. Attach domain routers here, e.g.:
    #   protected.include_router(new_product_router(product_service))
    protected = APIRouter(dependencies=[Depends(get_user_id)])
    v1.include_router(protected)

    app.include_router(v1)

    return app
