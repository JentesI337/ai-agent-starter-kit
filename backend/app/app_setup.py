from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

OnStartupFn = Callable[[], None | Awaitable[None]]
OnShutdownFn = Callable[[], None | Awaitable[None]]


def build_fastapi_app(*, title: str, settings) -> FastAPI:
    app = FastAPI(title=title)
    configure_cors(app=app, settings=settings)
    return app


def configure_cors(*, app: FastAPI, settings) -> None:
    cors_origins = list(settings.cors_allow_origins)
    if settings.app_env != "production" and not cors_origins:
        cors_origins = ["*"]

    cors_allow_credentials = settings.cors_allow_credentials
    if "*" in cors_origins:
        cors_allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
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
