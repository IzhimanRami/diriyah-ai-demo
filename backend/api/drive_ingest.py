# backend/api/drive_ingest.py

import logging
from fastapi import APIRouter, Query

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/drive/ingest")
async def api_ingest(folderId: str = Query(..., alias="folderId")):
    """
    TEMP: minimal ingest endpoint just to prove the routing / infra works.
    This should NEVER crash the worker – it only logs and echoes the folderId.
    """

    logger.info("INGEST TEST: received request for folder %s", folderId)

    # Just return something small & safe
    return {
        "status": "ok",
        "message": "Ingest TEST endpoint reached successfully",
        "folderId": folderId,
    }
