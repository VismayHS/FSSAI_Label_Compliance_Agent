"""App factory. Dependencies come from the registry (IMPL_*), so swapping in a teammate's real
implementation is an .env change. Routers live in app/routers/ and are mounted automatically:
add a module with a module-level `router = APIRouter()` and it appears, no edit here needed.

Routers reach shared services through `request.app.state`: `gate`, `run_store`, `dispatcher`, `settings`.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI
from fssai_observability import setup_logging, setup_tracing

from fssai_contracts.registry import build
from fssai_worker.dispatch import Dispatcher, from_environ
from fssai_worker.jobs import Deps

from . import observability, routers


@dataclass(frozen=True)
class Settings:
    max_request_bytes: int = 256 * 1024
    max_list_limit: int = 100

    @classmethod
    def from_env(cls) -> Settings:
        raw = os.environ.get("API_MAX_REQUEST_BYTES", "").split("#", 1)[0].strip()
        return cls(max_request_bytes=int(raw) if raw else cls.max_request_bytes)


def mount_routers(app: FastAPI) -> list[str]:
    mounted = []
    for info in sorted(pkgutil.iter_modules(routers.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{routers.__name__}.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
            mounted.append(info.name)
    return mounted


def create_app(*, gate=None, run_store=None, pipeline=None, dispatcher: Dispatcher | None = None,
               settings: Settings | None = None) -> FastAPI:
    setup_logging("api")
    setup_tracing("api")
    run_store = run_store or build("run_store")
    if dispatcher is None:  # a factory: only inline mode builds the pipeline inside the API
        dispatcher = from_environ(lambda: Deps(pipeline=pipeline or build("pipeline"), run_store=run_store))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        pool = getattr(app.state.dispatcher, "pool", None)
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
        close = getattr(app.state.run_store, "close", None)  # e.g. the Postgres store's connection pool
        if callable(close):
            close()

    app = FastAPI(title="FSSAI Label Compliance Agent", version="0.1.0", lifespan=lifespan,
                  description="Checks a packaged-food label against FSSAI regulations and returns findings "
                              "with citations and a route. It never approves a label; a regulatory affairs "
                              "professional decides.")
    app.state.gate = gate or build("gate")
    app.state.run_store = run_store
    app.state.dispatcher = dispatcher
    app.state.settings = settings or Settings.from_env()
    observability.install(app)
    app.state.routers = mount_routers(app)
    observability.event("api_started", dispatch=dispatcher.mode, routers=app.state.routers)
    return app
