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


class _SecurityHeaderMiddleware(BaseHTTPMiddleware):
    """SEC (API-05): Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # SEC (INFO-06): Strip server version information to prevent disclosure
        response.headers["Server"] = "app"
        return response


class _RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """SEC (API-03): Reject request bodies exceeding a configurable size limit."""

    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)


def build_fastapi_app(*, title: str, settings) -> FastAPI:
    # SEC (INFO-08): Disable OpenAPI/Swagger UI in production unless debug_mode is on
    is_prod = getattr(settings, "app_env", "development") == "production"
    show_docs = getattr(settings, "debug_mode", False) or not is_prod
    app = FastAPI(
        title=title,
        docs_url="/docs" if show_docs else None,
        redoc_url="/redoc" if show_docs else None,
        openapi_url="/openapi.json" if show_docs else None,
    )
    configure_cors(app=app, settings=settings)
    # SEC (OE-03): Add rate limiting middleware
    app.add_middleware(_RateLimitMiddleware)
    # SEC (API-05): Add security headers to all responses
    app.add_middleware(_SecurityHeaderMiddleware)
    # SEC (API-03): Enforce request body size limits
    app.add_middleware(_RequestSizeLimitMiddleware)
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
