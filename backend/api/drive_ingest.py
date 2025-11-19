# backend/api/drive_ingest.py
"""
Drive ingestion endpoint.

Uses the public Google Drive v3 API with an API key (no service account)
to list ALL files in a folder. This is the foundation for the later
Q&A / embeddings pipeline.
"""

from __future__ import annotations

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

# IMPORTANT:
#  - In production, set GOOGLE_DRIVE_API_KEY (or GOOGLE_API_KEY) in Render.
#  - The hard-coded key is just a fallback for this demo.
_GOOGLE_API_KEY = (
    os.environ.get("GOOGLE_DRIVE_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or "AIzaSyCt67CzFTVc-G0O6CuZZLs60uiaBsOXQtc"
)


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder.

    This matches the manual URL you tested in the browser:

      https://www.googleapis.com/drive/v3/files
        ?q='<FOLDER_ID>' in parents and trashed=false
        &key=YOUR_API_KEY
        &fields=files(id,name,mimeType,webViewLink,modifiedTime)
    """
    if not _GOOGLE_API_KEY:
        raise RuntimeError("Google Drive API key is not configured")

    query_str = f"'{folder_id}' in parents and trashed=false"

    params = {
        "q": query_str,
        "key": _GOOGLE_API_KEY,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
        # Be generous so we get everything in one call for the demo
        "pageSize": 1000,
        # Safer when working with shared drives as well
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }

    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params)

    logger.info("Calling Google Drive API for folder %s", folder_id)
    logger.debug("Google Drive URL: %s", url)

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        # Read the response body so we can see Google's real error message
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:  # pragma: no cover - very defensive
            body = ""

        logger.error(
            "Google Drive API HTTP %s for folder %s: %s",
            exc.code,
            folder_id,
            body,
        )
        raise RuntimeError(f"Google Drive API HTTP {exc.code}: {body}") from exc
    except Exception as exc:  # pragma: no cover - defensive
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

    For now this:
      * fetches the file list via API key
      * returns ALL files (any mimeType) as JSON

    Later we will:
      * download only text-bearing files (pdf, docx, pptx, xlsx, txt, etc.)
      * create embeddings using OpenAI
      * store them in a vector DB keyed by `chat_id` / project
    """
    logger.info("Starting ingest for folder %s (chat_id=%s)", folder_id, chat_id)

    try:
        files = _fetch_drive_files_via_api_key(folder_id)
        return {
            "folderId": folder_id,
            "chatId": chat_id,
            "fileCount": len(files),
            "files": files,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Drive ingest failed for folder %s", folder_id)
        # Return 500 JSON with the *full* message including Google's error
        raise HTTPException(
            status_code=500,
            detail=f"Drive ingest failed: {exc}",
        ) from exc
