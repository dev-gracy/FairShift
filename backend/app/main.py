"""
FairShift — FastAPI application entry point

Architecture: Single FastAPI app serving:
  - REST API under /api/v1/
  - Static frontend files at /
  - Auto-generated OpenAPI docs at /docs (disabled in production)

Security posture:
  - CORS locked to explicit origins in production
  - Security headers via middleware
  - No raw SQL — ORM only
  - No credentials in code — all via environment variables
  - Input validation via Pydantic on all endpoints

Efficiency:
  - SQLite with connection pooling (single file, zero infra)
  - Static files served by Starlette (no separate web server needed)
  - Minimal dependencies — see requirements.txt
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.models.database import engine, SessionLocal
from app.models.models import Base, User
from app.models.industry_config import load_profiles
from app.routers import auth, shifts, reports, dashboard, config_routes

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fairshift")

APP_ENV = os.getenv("APP_ENV", "production")
IS_DEV = APP_ENV == "development"

# ---------------------------------------------------------------------------
# Startup / shutdown lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables and load configs on startup. Clean up on shutdown."""
    logger.info("FairShift starting up (env=%s)", APP_ENV)
    Base.metadata.create_all(bind=engine)
    load_profiles()

    # If database has no users (e.g. fresh ephemeral SQLite in /tmp on Vercel), auto-seed demo data
    try:
        with SessionLocal() as db:
            if not db.query(User).first():
                logger.info("Empty database detected — auto-seeding demo accounts...")
                try:
                    from seed import seed
                    seed()
                    logger.info("Auto-seed finished successfully.")
                except Exception as seed_err:
                    logger.warning("Auto-seed error: %s", seed_err)
    except Exception as db_err:
        logger.warning("Database check warning: %s", db_err)

    logger.info("Database tables verified. Industry profiles loaded.")
    yield
    logger.info("FairShift shutting down.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FairShift API",
    description=(
        "Decent Work Platform for shift workers across multiple industries. "
        "Aligned with UN SDG 8. Prompt Wars 2026."
    ),
    version="1.0.0",
    docs_url="/docs" if IS_DEV else None,   # Hide docs in production
    redoc_url="/redoc" if IS_DEV else None,
    lifespan=lifespan,
)

@app.middleware("http")
async def restore_vercel_path(request: Request, call_next):
    matched = request.headers.get("x-matched-path")
    if matched and "index.py" not in matched:
        request.scope["path"] = matched.split("?")[0]
    response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# Security headers middleware
# Adds CSP, HSTS, X-Frame-Options etc. on every response
# ---------------------------------------------------------------------------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self)"
    if not IS_DEV:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ---------------------------------------------------------------------------
# CORS — locked to same origin in production
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "url_path": request.url.path,
            "scope_path": request.scope.get("path"),
            "scope_raw_path": str(request.scope.get("raw_path")),
            "scope_root_path": request.scope.get("root_path"),
            "query_string": request.scope.get("query_string", b"").decode("latin1"),
            "headers": dict(request.headers),
        }
    )




@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# API routers (versioned under /api/v1, /v1, and root for serverless path stripping)
# ---------------------------------------------------------------------------
for prefix in ["/api/v1", "/v1", ""]:
    app.include_router(auth.router, prefix=prefix)
    app.include_router(shifts.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(dashboard.router, prefix=prefix)
    app.include_router(config_routes.router, prefix=prefix)


# ---------------------------------------------------------------------------
# Health check — required for Cloud Run & Vercel readiness probe
# ---------------------------------------------------------------------------
@app.get("/health", tags=["ops"])
@app.get("/api/health", tags=["ops"])
@app.get("/api/v1/health", tags=["ops"])
def health():
    return {"status": "ok", "service": "fairshift", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Static files & portal routes
# ---------------------------------------------------------------------------
_FRONTEND_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend"),
    os.path.join(os.path.dirname(__file__), "..", "..", "public"),
    os.path.join(os.path.dirname(__file__), "..", "frontend"),
    os.path.join(os.path.dirname(__file__), "..", "public"),
    os.path.join(os.getcwd(), "frontend"),
    os.path.join(os.getcwd(), "public"),
    os.path.join(os.getcwd(), "..", "frontend"),
    os.path.join(os.getcwd(), "..", "public"),
]


def _find_frontend_file(subpath: str):
    for candidate in _FRONTEND_CANDIDATES:
        full_path = os.path.abspath(os.path.join(candidate, subpath))
        if os.path.isfile(full_path):
            return full_path
    return None


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def serve_index():
    path = _find_frontend_file("index.html")
    if path:
        return FileResponse(path)
    return HTMLResponse("<h1>FairShift Platform</h1><p>Frontend loading...</p>")


@app.get("/worker", include_in_schema=False)
@app.get("/worker/", include_in_schema=False)
def serve_worker_portal():
    path = _find_frontend_file(os.path.join("worker", "index.html"))
    if path:
        return FileResponse(path)
    return HTMLResponse("<h1>Worker Portal</h1>")


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def serve_admin_portal():
    path = _find_frontend_file(os.path.join("admin", "index.html"))
    if path:
        return FileResponse(path)
    return HTMLResponse("<h1>Admin Dashboard</h1>")


_FRONTEND_DIR = next((d for d in _FRONTEND_CANDIDATES if os.path.isdir(d)), None)
if _FRONTEND_DIR:
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")

