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

# You set BOTH GOOGLE_API_KEY and GOOGLE_DRIVE_API_KEY in Render.
# We'll try GOOGLE_DRIVE_API_KEY first, then fall back to GOOGLE_API_KEY.
_GOOGLE_API_KEY = os.environ.get("GOOGLE_DRIVE_API_KEY") or os.environ.get("GOOGLE_API_KEY")

if not _GOOGLE_API_KEY:
    logger.error("GOOGLE_DRIVE_API_KEY / GOOGLE_API_KEY not set in environment.")
    # Do NOT crash worker; just fail per-request.
    # FastAPI route will raise clean 500 if this is missing.


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder. This uses the *exact same* pattern that works
    when you paste the URL into the browser.
    """

    if not _GOOGLE_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Drive ingest misconfigured: GOOGLE_DRIVE_API_KEY / GOOGLE_API_KEY env var is not set",
        )

    # EXACT same query as your working browser URL:
    # q='FOLDER_ID' in parents and trashed=false
    query_str = f"'{folder_id}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder'"

    # Build URL *manually* to avoid any surprises
    base_url = "https://www.googleapis.com/drive/v3/files"

    url = (
        f"{base_url}"
        f"?q={urllib.parse.quote(query_str, safe='')}"
        f"&key={urllib.parse.quote(_GOOGLE_API_KEY, safe='')}"
        f"&fields={urllib.parse.quote('files(id,name,mimeType,webViewLink,modifiedTime)', safe=',()')}"
    )

    logger.info("Drive ingest: calling Google Drive API for folder %s", folder_id)
    logger.warning("Drive ingest DEBUG URL (copy into browser to compare): %s", url)

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

    For now:
      * fetch the file list via API key
      * return them as JSON so we can confirm everything works
    """
    logger.info("Starting ingest for folder %s (chat_id=%s)", folder_id, chat_id)

    files = _fetch_drive_files_via_api_key(folder_id)

    return {
        "folderId": folder_id,
        "chatId": chat_id,
        "fileCount": len(files),
        "files": files,
    }
