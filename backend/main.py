import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import (
    advanced_intelligence,
    alerts,
    analytics,
    autocad,
    cache,
    chat,
    connectors,
    drive,
    drive_diagnose,
    drive_scan,
    openai_test,
    parsing,
    preferences,
    project,
    projects,
    qto,
    speech,
    upload,
    users,
    vision,
    workspace,  # existing workspace module under backend.api (kept)
)
from backend.services.google_drive import (
    drive_credentials_available,
    drive_service_error,
    drive_stubbed,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Diriyah Brain AI", version="v1.24")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_BASE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BASE_DIR.parent
_FRONTEND_DIST_DIR = _PROJECT_ROOT / "frontend_dist"
_FRONTEND_PUBLIC_DIR = _PROJECT_ROOT / "frontend" / "public"

if _FRONTEND_PUBLIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=_FRONTEND_PUBLIC_DIR), name="static")
else:
    logger.warning("frontend public assets directory %s is missing", _FRONTEND_PUBLIC_DIR)

if _FRONTEND_DIST_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=_FRONTEND_DIST_DIR / "assets", check_dir=False),
        name="assets",
    )
    _INDEX_HTML = _FRONTEND_DIST_DIR / "index.html"
else:
    _INDEX_HTML = _FRONTEND_PUBLIC_DIR / "index.html"

if not _INDEX_HTML.exists():
    logger.warning("frontend index file %s is missing", _INDEX_HTML)
    _INDEX_HTML = None


def _include_router_if_available(module, tag: str) -> None:
    """Register the router exposed by ``module`` when present."""
    router = getattr(module, "router", None)
    if router is not None:
        app.include_router(router, prefix="/api", tags=[tag])


# Register all built-in routers that live directly under backend.api.*
for module, tag in (
    (advanced_intelligence, "Advanced Intelligence"),
    (autocad, "AutoCAD"),
    (chat, "Chat"),
    (connectors, "Connectors"),
    (project, "Intel"),
    (cache, "Cache"),
    (alerts, "Alerts"),
    (analytics, "Analytics"),
    (drive, "Drive"),
    (openai_test, "OpenAI"),
    (parsing, "Parsing"),
    (upload, "Upload"),
    (qto, "QTO"),
    (vision, "Vision"),
    (speech, "Speech"),
    (projects, "Projects"),
    (preferences, "Preferences"),
    (drive_scan, "Drive"),
    (drive_diagnose, "Drive"),
    (users, "Users"),
    (workspace, "Workspace"),  # keeps existing backend.api.workspace if present
):
    _include_router_if_available(module, tag)

# --------------------------------------------------------------------
# NEW: Explicitly include the routes we added at backend/api/routes/workspace.py
# That file defines: router = APIRouter(prefix="/api/workspace", tags=["workspace"])
# We do NOT add another prefix here to avoid /api/api/workspace.
# --------------------------------------------------------------------
try:
    from backend.api.routes import workspace as workspace_routes  # type: ignore

    if hasattr(workspace_routes, "router"):
        app.include_router(workspace_routes.router)
        logger.info("Registered routes from backend.api.routes.workspace")
    else:
        logger.warning("backend.api.routes.workspace has no 'router' attribute")
except Exception as e:
    logger.warning("Could not register backend.api.routes.workspace: %s", e)
# --------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def serve_frontend() -> FileResponse:
    if _INDEX_HTML is None:
        raise HTTPException(status_code=404, detail="Frontend assets are not available")
    return FileResponse(_INDEX_HTML, media_type="text/html")


@app.get("/health")
def health_check():
    error = drive_service_error()
    return {
        "status": "ok" if error is None else "degraded",
        "version": "v1.24",
        "drive": {
            "credentials_available": drive_credentials_available(),
            "stubbed": drive_stubbed(),
            "error": error,
        },
    }
