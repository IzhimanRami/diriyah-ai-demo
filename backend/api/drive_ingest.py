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

# ---------------------------------------------------------------------------
# Google Drive API helper using API KEY (no service account)
# ---------------------------------------------------------------------------

# In production, move this to an env var and REMOVE the hard-coded fallback.
_GOOGLE_API_KEY = os.environ.get("GOOGLE_DRIVE_API_KEY")

if not _GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_DRIVE_API_KEY env var is not set")

_DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder. This should mirror the URL that works in your browser.
    """
    if not _GOOGLE_API_KEY:
        raise RuntimeError("Google Drive API key is not configured")

    # Same query pattern you used in the browser:
    query_str = f"'{folder_id}' in parents and trashed=false"

    params = {
        "q": query_str,
        "key": _GOOGLE_API_KEY,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
        # These help with shared drives / “My Drive” edge cases
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
        # Surface as 502 to the frontend so we don't confuse it with our own 4xx.
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
      * fetch the file list via API key
      * return them as JSON so we can confirm everything works

    Later:
      * for each file, download + embed + store in vector DB
      * link the embeddings to the given chat_id (e.g. 'villa-ops')
    """
    logger.info("Starting ingest for folder %s (chat_id=%s)", folder_id, chat_id)

    files = _fetch_drive_files_via_api_key(folder_id)

    return {
        "folderId": folder_id,
        "chatId": chat_id,
        "fileCount": len(files),
        "files": files,
    }
