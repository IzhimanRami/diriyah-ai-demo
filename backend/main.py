from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.services.google_drive import (
    drive_stubbed,
    drive_credentials_available,
    drive_service_error,
    list_folder_items,
    download_file_bytes,
    upload_to_drive,  # kept for backward compatibility; returns "unsupported-api-key-mode"
)

# NOTE:
# main.py mounts this router with prefix="/api", so all routes below end up as:
#   /api/drive/diagnostics
#   /api/drive/list
#   /api/drive/download/{file_id}
#   /api/drive/upload
router = APIRouter(prefix="/drive", tags=["Drive"])


@router.get("/diagnostics")
def diagnostics():
    return {
        "mode": "api-key-public-folder-readonly",
        "stubbed": drive_stubbed(),
        "credentialsAvailable": drive_credentials_available(),
        "lastError": drive_service_error(),
    }


@router.get("/list")
def list_items():
    """List files in the configured public folder (requires public sharing)."""
    items = list_folder_items()
    return {"items": items}


@router.get("/download/{file_id}")
def download(file_id: str):
    """Download a publicly shared file by ID (alt=media)."""
    try:
        data = download_file_bytes(file_id)
        return StreamingResponse(iter([data]), media_type="application/octet-stream")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/upload")
def upload_not_supported():
    """
    Placeholder for old clients. API-key mode can't upload.
    Returns a deterministic token describing the limitation.
    """
    token = upload_to_drive(None)
    return {"status": "unsupported", "token": token}
