# backend/api/drive_ingest.py
"""
Drive ingest endpoint.

For now this:
  * lists ALL files in a given Google Drive folder (no MIME-type filter)
  * returns them as JSON so the frontend / console can consume them

Later we can plug in:
  - per-file content download
  - chunking + embeddings
  - vector search tied to chatId / project
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()

# ------------------------------------------------------------------------------
# Google Drive API helper using API KEY (no service account)
# ------------------------------------------------------------------------------

# In production, move this to an env var and REMOVE the hard-coded fallback.
_GOOGLE_API_KEY: str = (
    os.environ.get("GOOGLE_DRIVE_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or "AIzaSyCt67CzFTVc-G0O6CuZZLs60uiaBsOXQtc"  # <- demo fallback
)


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder. This mirrors the URL you tested in the browser.

    NOTE: We ONLY *list* here – no file download, no export. That keeps the
    endpoint simple and avoids 400 errors from per-file calls.
    """
    if not _GOOGLE_API_KEY:
        raise RuntimeError("Google Drive API key is not configured")

    # Same query pattern you used manually:
    #   q='%FOLDER%' in parents and trashed=false
    query_str = f"'{folder_id}' in parents and trashed=false"

    params = {
        "q": query_str,
        "key": _GOOGLE_API_KEY,
        # IMPORTANT: we do NOT filter by mimeType -> ALL file types are returned
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
    }

    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params)
    logger.info("Calling Google Drive API for folder %s", folder_id)

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error calling Google Drive API")
        # Bubble up as 502 from *our* API, instead of letting it crash the worker
        raise HTTPException(
            status_code=502,
            detail=f"HTTP error calling Google Drive API: {exc}",
        ) from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to decode Google Drive response as JSON")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to parse Google Drive response: {exc}",
        ) from exc

    files = data.get("files", [])
    logger.info("Google Drive returned %d files for folder %s", len(files), folder_id)
    return files


# ------------------------------------------------------------------------------
# Ingest endpoint
# ------------------------------------------------------------------------------


@router.api_route("/drive/ingest", methods=["POST", "GET"])
async def ingest_drive_folder(
    folder_id: str = Query(..., alias="folderId"),
    chat_id: Optional[str] = Query(None, alias="chatId"),
):
    """
    Ingest a Google Drive folder.

    CURRENT BEHAVIOUR:
      * Fetch list of ALL files via API key.
      * Return metadata to the caller.
      * `chatId` is accepted for future use (linking ingestion to a conversation),
        but is not yet used in any server-side logic.

    This keeps the endpoint fast and reliable while we wire up the
    embeddings / vector store in a second step.
    """
    logger.info("Starting ingest for folder %s (chatId=%s)", folder_id, chat_id)

    try:
        files = _fetch_drive_files_via_api_key(folder_id)
    except HTTPException:
        # Already logged and wrapped with an HTTPException above.
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Drive ingest failed for folder %s", folder_id)
        raise HTTPException(
            status_code=500,
            detail=f"Drive ingest failed: {exc}",
        ) from exc

    return {
        "folderId": folder_id,
        "chatId": chat_id,
        "fileCount": len(files),
        "files": files,
    }
