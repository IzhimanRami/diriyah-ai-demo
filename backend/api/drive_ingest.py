# backend/api/drive_ingest.py

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()

# ------------------------------------------------------------------------------
# Google Drive API helper using API KEY (no service account)
# ------------------------------------------------------------------------------

# In production, move this to an env var and REMOVE the hard-coded fallback.
_GOOGLE_API_KEY = (
    os.environ.get("GOOGLE_DRIVE_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or "AIzaSyCt67CzFTVc-G0O6CuZZLs60uiaBsOXQtc"  # <- fallback for this demo
)


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder. This mirrors the URL you tested in the browser.
    """
    if not _GOOGLE_API_KEY:
        raise RuntimeError("Google Drive API key is not configured")

    # Same query you used:
    #   q='%FOLDER%' in parents and trashed=false
    query_str = f"'{folder_id}' in parents and trashed=false"

    params = {
        "q": query_str,
        "key": _GOOGLE_API_KEY,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
    }

    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params)

    logger.info("Calling Google Drive API for folder %s", folder_id)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read()
    except Exception as exc:
        logger.exception("Error calling Google Drive API")
        raise RuntimeError(f"HTTP error calling Google Drive API: {exc}") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        logger.exception("Failed to decode Google Drive response as JSON")
        raise RuntimeError(f"Failed to parse Google Drive response: {exc}") from exc

    files = data.get("files", [])
    logger.info("Google Drive returned %d files for folder %s", len(files), folder_id)
    return files


# ------------------------------------------------------------------------------
# Ingest endpoint
# ------------------------------------------------------------------------------


@router.api_route("/drive/ingest", methods=["POST", "GET"])
async def ingest_drive_folder(
    folder_id: str = Query(..., alias="folderId"),
):
    """
    Ingest a Google Drive folder.

    For now this:
      * fetches the file list via API key
      * returns them as JSON so we can confirm everything works

    Later we can plug in the vector DB / Chroma logic on top of this list.
    """
    logger.info("Starting ingest for folder %s", folder_id)

    try:
        files = _fetch_drive_files_via_api_key(folder_id)
        return {
            "folderId": folder_id,
            "fileCount": len(files),
            "files": files,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Drive ingest failed for folder %s", folder_id)
        # IMPORTANT: we return 500 JSON instead of crashing the worker,
        # so Render will NOT show 502.
        raise HTTPException(
            status_code=500,
            detail=f"Drive ingest failed: {exc}",
        ) from exc
