from fastapi import APIRouter, Query
from backend.jobs.drive_sync import ingest_folder

router = APIRouter()


@router.post("/drive/ingest")
async def api_ingest(folderId: str = Query(..., alias="folderId")):
    """
    Trigger the Google Drive → Chroma ingestion.
    """
    await ingest_folder(folderId)

    return {
        "status": "ok",
        "message": f"Folder {folderId} ingested successfully"
    }
