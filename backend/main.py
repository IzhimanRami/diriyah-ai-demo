# backend/main.py
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import your Drive router (defined in backend/api/drive.py)
from backend.api.drive import router as drive_router

APP_NAME = os.getenv("APP_NAME", "Diriyah AI Demo")

app = FastAPI(
    title=APP_NAME,
    version=os.getenv("APP_VERSION", "1.0.0"),
    docs_url="/docs",
    redoc_url="/redoc",
)

# --------------------------- CORS (adjust as needed) ---------------------------

# Allow localhost (dev) and onrender.com (prod)
allowed_origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
]

# If running on Render, also allow the public URL
render_external_url = os.getenv("RENDER_EXTERNAL_URL")
if render_external_url:
    allowed_origins.append(render_external_url)
    # Also allow wildcard *.onrender.com if you prefer:
    # NOTE: For stricter security, list your exact host instead of wildcard.
    allowed_origins.append("https://*.onrender.com")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins + ["*"],  # relax during bring-up; tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------- Routers mounting --------------------------------

# All Drive routes end up as:
#   /api/drive/diagnostics
#   /api/drive/list
#   /api/drive/download/{file_id}
#   /api/drive/upload
app.include_router(drive_router, prefix="/api")

# ------------------------------- Health & root ---------------------------------

@app.get("/healthz", tags=["System"])
def healthz():
    return {"status": "ok", "service": APP_NAME}

@app.get("/", tags=["System"])
def root():
    return {"message": f"{APP_NAME} backend is up", "docs": "/docs", "health": "/healthz"}
