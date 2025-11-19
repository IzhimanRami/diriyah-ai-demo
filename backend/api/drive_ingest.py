# backend/api/drive_ingest.py

import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()

# Base URL for Drive v3
_DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """
    Read the Google API key from the environment.

    We allow either GOOGLE_DRIVE_API_KEY or GOOGLE_API_KEY.
    If neither is set, we return a clean 500 error to the frontend
    (but we DO NOT crash the worker at import time).
    """
    api_key = (
        os.environ.get("GOOGLE_DRIVE_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )

    if not api_key:
        # Endpoint cannot work until you configure the key in Render.
        raise HTTPException(
            status_code=500,
            detail=(
                "GDRIVE_API_KEY not set – configure GOOGLE_DRIVE_API_KEY "
                "or GOOGLE_API_KEY in Render dashboard."
            ),
        )

    return api_key


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder. Mirrors the URL you tested directly in the browser.
    """
    api_key = _get_api_key()

    # Same query pattern as in your manual test:
    #    q='<folder_id>' in parents and trashed=false
    query_str = f"'{folder_id}' in parents and trashed=false"

    params = {
        "q": query_str,
        "key": api_key,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }

    url = _DRIVE_LIST_URL + "?" + urllib.parse.urlencode(params)

    logger.info("Drive ingest: calling Google Drive API for folder %s", folder_id)
    logger.debug("Drive ingest URL: %s", url)

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        logger.error(
            "Google Drive API HTTP error %s while ingesting folder %s: %s",
            exc.code,
            folder_id,
            body,
        )
        # 502 = “upstream” problem; keeps it separate from our own 4xx.
        raise HTTPException(
            status_code=502,
            detail=f"Drive ingest failed: Google Drive API HTTP {exc.code}: {body}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Network/unknown error calling Google Drive API")
        raise HTTPException(
            status_code=502,
            detail=f"Drive ingest failed: {exc}",
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


# ---------------------------------------------------------------------------
# Ingest endpoint
# ---------------------------------------------------------------------------

@router.api_route("/drive/ingest", methods=["POST", "GET"])
async def ingest_drive_folder(
    folder_id: str = Query(..., alias="folderId"),
    chat_id: Optional[str] = Query(None, alias="chatId"),
):
    """
    Ingest a Google Drive folder.

    Current behaviour:
      * Fetch the file list via API key
      * Return them as JSON for debugging

    Later:
      * For each file: download + embed + store in vector DB
      * Link those embeddings to the given chat_id (e.g. 'villa-ops')
    """
    logger.info("Starting ingest for folder %s (chat_id=%s)", folder_id, chat_id)

    files = _fetch_drive_files_via_api_key(folder_id)

    return {
        "folderId": folder_id,
        "chatId": chat_id,
        "fileCount": len(files),
        "files": files,
    }
