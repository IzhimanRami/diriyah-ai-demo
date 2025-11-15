from fastapi import APIRouter, Query
import asyncio
from backend.jobs.drive_sync import ingest_folder

router = APIRouter()


@router.post("/drive/ingest")
async def api_ingest(folderId: str = Query(..., alias="folderId")):
    """
    Trigger the Google Drive → Chroma ingestion.

    IMPORTANT:
    ingest_folder() is synchronous, so we run it in a thread.
    """

    # Run ingestion in a background thread (non-blocking)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, ingest_folder, folderId)

    return {
        "status": "ok",
        "message": f"Folder {folderId} ingested successfully"
    }
