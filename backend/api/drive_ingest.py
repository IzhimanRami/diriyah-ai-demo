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
from fastapi import APIRouter, Query, HTTPException
import asyncio
import logging

from backend.jobs.drive_sync import ingest_folder

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/drive/ingest")
async def api_ingest(folderId: str = Query(..., alias="folderId")):
    """
    Trigger the Google Drive → Chroma ingestion.
    """

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, ingest_folder, folderId)

        return {
            "status": "ok",
            "message": f"Folder {folderId} ingested successfully",
            "result": result,
        }

    except Exception as e:
        logger.exception("Drive ingest failed")
        # Surface the real error to the client so you see it in the browser/console
        raise HTTPException(status_code=500, detail=str(e))
