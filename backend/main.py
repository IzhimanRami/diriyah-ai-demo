# backend/main.py
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Routers
from backend.api.drive import router as drive_router
from backend.api.workspace import router as workspace_router

APP_NAME = os.getenv("APP_NAME", "Diriyah AI Demo")

app = FastAPI(
    title=APP_NAME,
    version=os.getenv("APP_VERSION", "1.0.0"),
    docs_url="/docs",
    redoc_url="/redoc",
)

# --------------------------- CORS (adjust as needed) ---------------------------
allowed_origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
]

render_external_url = os.getenv("RENDER_EXTERNAL_URL")
if render_external_url:
    allowed_origins.append(render_external_url)
    allowed_origins.append("https://*.onrender.com")  # optional wildcard

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins + ["*"],  # relax during bring-up; tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------- Routers mounting --------------------------------
# Drive endpoints:
#   /api/drive/diagnostics, /api/drive/list, /api/drive/download/{file_id}, /api/drive/upload
app.include_router(drive_router, prefix="/api")

# Workspace endpoints (frontend expects /api/workspace/*)
app.include_router(workspace_router, prefix="/api")

# ------------------------------- Health & root ---------------------------------
@app.get("/healthz", tags=["System"])
def healthz():
    return {"status": "ok", "service": APP_NAME}

@app.get("/", tags=["System"])
def root():
    return {"message": f"{APP_NAME} backend is up", "docs": "/docs", "health": "/healthz"}
