# backend/api/drive_ingest.py

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()

DRIVE_API_KEY = os.environ.get("GOOGLE_DRIVE_API_KEY")
DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"


def _build_params(folder_id: str) -> Dict[str, Any]:
    # EXACTLY the same query that works in your browser:
    # q='FOLDER_ID' in parents and trashed=false
    q = f"'{folder_id}' in parents and trashed=false"

    return {
        "q": q,
        "key": DRIVE_API_KEY,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }


@router.api_route("/drive/ingest", methods=["GET", "POST"])
async def ingest_drive_folder(
    folder_id: str = Query(..., alias="folderId"),
    chat_id: Optional[str] = Query(None, alias="chatId"),
):
    """
    Ingest a public Google Drive folder using only an API key.

    For now we:
      - call the Google Drive list API
      - return the files JSON directly so we can see it in the frontend
    """

    if not DRIVE_API_KEY:
        logger.error("GOOGLE_DRIVE_API_KEY is not set in the environment")
        raise HTTPException(
            status_code=500,
            detail="Drive ingest misconfigured: GOOGLE_DRIVE_API_KEY is not set",
        )

    params = _build_params(folder_id)

    logger.info("Drive ingest: listing folder %s", folder_id)
    logger.debug("Drive ingest params: %r", params)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(DRIVE_LIST_URL, params=params)
        except Exception as exc:  # network / DNS issues
            logger.exception("Network error calling Google Drive API")
            raise HTTPException(
                status_code=502,
                detail=f"Drive ingest failed: {exc}",
            ) from exc

    # If Google returned an error, forward it as JSON so you see the exact body
    if resp.status_code != 200:
        logger.error(
            "Google Drive API error %s for folder %s: %s",
            resp.status_code,
            folder_id,
            resp.text,
        )
        # IMPORTANT: resp.text is already JSON from Google
        raise HTTPException(
            status_code=502,
            detail={
                "status": resp.status_code,
                "body": resp.text,
            },
        )

    data = resp.json()
    files: List[Dict[str, Any]] = data.get("files", [])

    logger.info(
        "Drive ingest OK for folder %s: %d files returned",
        folder_id,
        len(files),
    )

    # Wrap Google result so the frontend can use it directly
    return {
        "folderId": folder_id,
        "chatId": chat_id,
        "fileCount": len(files),
        "files": files,
    }
