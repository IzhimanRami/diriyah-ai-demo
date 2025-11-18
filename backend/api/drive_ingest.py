# backend/api/drive_ingest.py

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Query

from backend.jobs.drive_sync import ingest_folder

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/drive/ingest")
async def api_ingest(folderId: str = Query(..., alias="folderId")):
    """
    Trigger the Google Drive → Chroma ingestion.

    We run the blocking ingest_folder() inside a thread so we don't
    block the event loop. Any exception is caught and returned as a
    normal 500 error instead of crashing the worker (which was causing 502).
    """

    # Always get / create an event loop safely
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        # Run the heavy sync job in a background thread
        await loop.run_in_executor(None, ingest_folder, folderId)

    except Exception as exc:
        # Log full traceback to Render logs so we can see the real cause
        logger.exception("Error ingesting Google Drive folder %s", folderId)
        raise HTTPException(
            status_code=500,
            detail=f"Ingest failed for folder {folderId}: {exc}",
        )

    return {
        "status": "ok",
        "message": f"Folder {folderId} ingested successfully",
    }
