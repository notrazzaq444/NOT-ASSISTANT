"""FastAPI application entry point for NOT."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import init_firebase
from .config import get_settings
from .database import init_db
from .models import HealthResponse
from .routes import auth as auth_routes
from .routes import chat as chat_routes
from .routes import conversations as convo_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("not")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    s = get_settings()
    log.info(
        "NOT starting. Model=%s, API key configured=%s, Auth configured=%s",
        s.openai_model, s.api_key_configured, s.auth_configured,
    )
    if s.auth_configured:
        try:
            init_firebase()
        except Exception as e:
            log.error("Firebase init failed at startup: %s", e)
    else:
        log.warning(
            "Firebase is NOT configured. Set GOOGLE_APPLICATION_CREDENTIALS "
            "in .env to enable authentication."
        )
    yield
    log.info("NOT shutting down.")


app = FastAPI(
    title="NOT",
    description="A JARVIS-style AI assistant.",
    version="2.0.0",
    lifespan=lifespan,
)

_settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Access-Token"],
)

app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(convo_routes.router)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    s = get_settings()
    return HealthResponse(
        status="ok",
        api_key_configured=s.api_key_configured,
        model=s.openai_model,
        auth_configured=s.auth_configured,
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/login", include_in_schema=False)
async def login_page() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "login.html"))


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "favicon.svg"))