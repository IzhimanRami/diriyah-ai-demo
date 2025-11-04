from fastapi import APIRouter, UploadFile, File
from backend.services import google_drive

router = APIRouter()


@router.get("/drive/diagnostics")
def drive_diagnostics():
    """
    Public diagnostics. Shows whether the backend is in public mode and can list
    the contents of the configured Master folder.
    """
    return google_drive.public_diagnostics()


# Backward compatible alias
@router.get("/drive/diagnose")
def drive_diagnose():
    return drive_diagnostics()


@router.get("/drive/scan/status")
def drive_scan_status():
    """
    Very light 'scan' status for the public mode.
    """
    if not google_drive.public_mode_enabled():
        return {"status": "idle", "detail": "Public mode is not configured."}

    files, _ = google_drive.list_public_children(page_size=25)
    return {"status": "ok", "count": len(files), "preview": files[:5]}


@router.post("/drive/upload")
async def drive_upload(file: UploadFile = File(...)):
    """
    Upload only works in private service-account mode. In public mode we return a stub.
    """
    file_id = google_drive.upload_to_drive(file)
    return {"file_id": file_id}
