from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from backend.services.google_drive import (
    upload_to_drive,          # stubbed in API-key mode
    diagnostics as drive_diag,
    list_folder_items,
    download_file_bytes,
)

router = APIRouter()

# ------------------ Upload (stubbed in API-key mode) ------------------------

@router.post("/drive/upload")
async def drive_upload(file: UploadFile = File(...)):
    """
    Upload is NOT supported in API-key public-folder mode.
    We keep this endpoint to avoid breaking callers; it returns a fixed token.
    """
    file_id = upload_to_drive(file)
    return {"file_id": file_id}


# ------------------ Diagnostics & Public Folder Listing ---------------------

@router.get("/drive/diagnostics")
def drive_diagnostics():
    """
    Returns current Drive integration status.
    Expected to include:
      - mode: "api-key-public-folder-readonly"
      - stubbed: bool
      - has_api_key / has_public_folder_id
      - public_folder_id (short)
      - last_error (if any)
    """
    return drive_diag()


@router.get("/drive/list")
def drive_list(
    page_token: str | None = Query(default=None, description="Drive page token"),
    page_size: int = Query(default=100, ge=1, le=1000),
):
    """
    Lists files from the configured PUBLIC folder using only an API key.
    The folder AND items must be shared as: Anyone with the link → Viewer.
    """
    data = list_folder_items(page_token=page_token, page_size=page_size)
    return JSONResponse(data)


# ------------------ Optional: direct download by file_id --------------------

@router.get("/drive/download/{file_id}")
def drive_download(file_id: str):
    """
    Streams the raw bytes of a publicly shared file (alt=media).
    Useful for simple fetches without exposing your API key to the browser.
    """
    try:
        content = download_file_bytes(file_id)
    except Exception as exc:  # propagate a clean 502/500 instead of stack trace
        raise HTTPException(status_code=502, detail=str(exc))

    return StreamingResponse(iter([content]), media_type="application/octet-stream")
