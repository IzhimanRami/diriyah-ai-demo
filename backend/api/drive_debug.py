# backend/api/drive_debug.py

from fastapi import APIRouter, Query, HTTPException

from backend.services.drive_service import list_files_in_folder

router = APIRouter(prefix="/drive", tags=["drive-debug"])


@router.get("/debug-list")
def debug_list(folderId: str = Query(..., alias="folderId")):
    """
    Simple debug endpoint to verify Drive API access.
    """
    try:
        files = list_files_in_folder(folderId)
        return {"files": files}
    except Exception as e:
        # Surface the real reason if something goes wrong
        raise HTTPException(status_code=500, detail=str(e))
