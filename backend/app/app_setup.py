from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.rate_limiter import get_rest_rate_limiter

OnStartupFn = Callable[[], None | Awaitable[None]]
OnShutdownFn = Callable[[], None | Awaitable[None]]


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """SEC (OE-03): Per-IP rate limiting middleware for REST endpoints."""

    async def dispatch(self, request: Request, call_next):
        limiter = get_rest_rate_limiter()
        if limiter.enabled:
            client_ip = request.client.host if request.client else "unknown"
            if not limiter.allow(client_ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please slow down."},
                    headers={"Retry-After": "1"},
                )
        return await call_next(request)


def build_fastapi_app(*, title: str, settings) -> FastAPI:
    app = FastAPI(title=title)
    configure_cors(app=app, settings=settings)
    # SEC (OE-03): Add rate limiting middleware
    app.add_middleware(_RateLimitMiddleware)
    return app


def configure_cors(*, app: FastAPI, settings) -> None:
    cors_origins = list(settings.cors_allow_origins)
    if settings.app_env != "production" and not cors_origins:
        # SEC: Even in development, default to localhost origins rather than
        # wildcard to prevent cross-origin attacks from malicious websites.
        cors_origins = ["http://localhost:4200", "http://localhost:3000", "http://127.0.0.1:4200", "http://127.0.0.1:3000"]

    cors_allow_credentials = settings.cors_allow_credentials
    if "*" in cors_origins:
        cors_allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


def build_lifespan_context(*, on_startup: OnStartupFn, on_shutdown: OnShutdownFn):
    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        startup_result = on_startup()
        if inspect.isawaitable(startup_result):
            await startup_result
        try:
            yield
        finally:
            shutdown_result = on_shutdown()
            if inspect.isawaitable(shutdown_result):
                await shutdown_result

    return _lifespan
