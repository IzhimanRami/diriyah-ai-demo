# backend/api/drive_ingest.py
DOWNLOAD_URL = "https://www.googleapis.com/drive/v3/files/{file_id}"

def _download_drive_file(file_id: str, mime_type: str) -> bytes:
    """
    Download the file content from Google Drive using the API key.

    For Google Docs/Sheets/Slides you can add special export logic later.
    For now we handle 'normal' files like PDFs, text, Word, etc.
    """
    params = {
        "alt": "media",
        "key": _GOOGLE_API_KEY,
    }
    url = DOWNLOAD_URL.format(file_id=file_id) + "?" + urllib.parse.urlencode(params)

    logger.info("Downloading Drive file %s", file_id)

    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        logger.warning(
            "Failed to download file %s from Drive: HTTP %s %s",
            file_id,
            exc.code,
            body,
        )
        raise

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

DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"


def _get_api_key() -> str:
    api_key = os.environ.get("GOOGLE_DRIVE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_DRIVE_API_KEY is NOT set in environment")
        raise HTTPException(
            status_code=500,
            detail="Drive ingest misconfigured: GOOGLE_DRIVE_API_KEY env var is not set",
        )
    return api_key


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the Google Drive v3 'files.list' endpoint using an API key.
    """

    api_key = _get_api_key()

    # Build the *same* query that works in your browser:
    query_str = f"'{folder_id}' in parents and trashed=false"

    params = {
        "q": query_str,
        "key": api_key,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }

    url = DRIVE_LIST_URL + "?" + urllib.parse.urlencode(params)

    # LOG EXACT URL + status so we can compare with the browser
    logger.info("DRIVE DEBUG URL: %s", url)

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            status = getattr(resp, "status", None)
            raw = resp.read()
            logger.info("DRIVE DEBUG HTTP status from Google: %s", status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        logger.error(
            "Google Drive API HTTP error %s while ingesting folder %s: %s",
            exc.code,
            folder_id,
            body,
        )
        # Return a clean JSON 502 up to the frontend
        raise HTTPException(
            status_code=502,
            detail=f"Drive ingest failed: Google Drive API HTTP {exc.code}: {body}",
        ) from exc
    except Exception as exc:  # network / DNS etc.
        logger.exception("Network/unknown error calling Google Drive API")
        raise HTTPException(
            status_code=502,
            detail=f"Drive ingest failed: {exc}",
        ) from exc

    # Try to decode JSON – if it fails, log the raw bytes
    try:
        text = raw.decode("utf-8")
        logger.debug("DRIVE DEBUG first 500 bytes: %s", text[:500])
        data = json.loads(text)
    except Exception as exc:
        logger.exception("Failed to decode Google Drive response as JSON")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to parse Google Drive response: {exc}",
        ) from exc

    files = data.get("files", [])
    logger.info("Google Drive returned %d files for folder %s", len(files), folder_id)
    return files


@router.api_route("/drive/ingest", methods=["POST", "GET"])
async def ingest_drive_folder(
    folder_id: str = Query(..., alias="folderId"),
    chat_id: Optional[str] = Query(None, alias="chatId"),
):
    """
    Ingest a Google Drive folder (for now: just list the files).
    """
    logger.info("Starting ingest for folder %s (chat_id=%s)", folder_id, chat_id)

    files = _fetch_drive_files_via_api_key(folder_id)

    # Simple JSON response for the frontend
    return {
        "folderId": folder_id,
        "chatId": chat_id,
        "fileCount": len(files),
        "files": files,
    }
