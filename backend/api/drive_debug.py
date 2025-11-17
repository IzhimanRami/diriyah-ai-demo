from fastapi import APIRouter, Query, HTTPException
from backend.services.drive_service import list_files_in_folder  # name may differ

router = APIRouter()

@router.get("/drive/debug-list")
def debug_list(folderId: str = Query(..., alias="folderId")):
    try:
        files = list_files_in_folder(folderId)
        # return only id/name to keep it small
        return {
            "status": "ok",
            "count": len(files),
            "files": [
                {"id": f.get("id"), "name": f.get("name"), "mimeType": f.get("mimeType")}
                for f in files
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
