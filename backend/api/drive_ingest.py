from fastapi import APIRouter, Query
from backend.jobs.drive_sync import ingest_folder

router = APIRouter()


@router.post("/drive/ingest")
async def api_ingest(folderId: str = Query(..., alias="folderId")):
    """
    Trigger the Google Drive → Chroma ingestion.
    """

    # ingest_folder is async now, so we just await it
    result = await ingest_folder(folderId)
    return result
