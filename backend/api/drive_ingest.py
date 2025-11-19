# backend/api/drive_ingest.py

import json
import logging
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAY_SEC = 2  # seconds between retries

# Try all possible env vars so we don't accidentally pick the wrong one
_GOOGLE_API_KEY = (
    os.environ.get("GOOGLE_DRIVE_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or os.environ.get("GDRIVE_API_KEY")
)

if not _GOOGLE_API_KEY:
    logger.warning(
        "No Google Drive API key found in env vars "
        "(GOOGLE_DRIVE_API_KEY / GOOGLE_API_KEY / GDRIVE_API_KEY). "
        "Drive ingest will return 500 until this is configured."
    )

_DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder, with simple retry logic.
    """

    if not _GOOGLE_API_KEY:
        # Per-request failure instead of crashing the worker at startup
        raise HTTPException(
            status_code=500,
            detail=(
                "Drive ingest misconfigured: no Google Drive API key found in "
                "GOOGLE_DRIVE_API_KEY / GOOGLE_API_KEY / GDRIVE_API_KEY"
            ),
        )

    query_str = f"'{folder_id}' in parents and trashed=false"

    params = {
        "q": query_str,
        "key": _GOOGLE_API_KEY,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }

    url = _DRIVE_LIST_URL + "?" + urllib.parse.urlencode(params)

    raw: bytes | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "Drive ingest: calling Google Drive API for folder %s (attempt %d/%d)",
            folder_id,
            attempt,
            MAX_RETRIES,
        )
        logger.debug("Drive ingest URL: %s", url)

        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                raw = resp.read()
            logger.info("Drive API call successful on attempt %d", attempt)
            break  # success

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            logger.warning(
                "Google Drive API HTTP error %s on attempt %d for folder %s: %s",
                exc.code,
                attempt,
                folder_id,
                body,
            )
            if attempt == MAX_RETRIES:
                logger.error(
                    "All %d retries failed for folder %s (HTTP %s)",
                    MAX_RETRIES,
                    folder_id,
                    exc.code,
                )
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Drive ingest failed after {MAX_RETRIES} attempts: "
                        f"Google Drive API HTTP {exc.code}: {body}"
                    ),
                ) from exc
            time.sleep(RETRY_DELAY_SEC)

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Network/unknown error calling Google Drive API on attempt %d",
                attempt,
            )
            if attempt == MAX_RETRIES:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Drive ingest failed after {MAX_RETRIES} attempts: {exc}"
                    ),
                ) from exc
            time.sleep(RETRY_DELAY_SEC)

    if raw is None:
        logger.error(
            "Drive ingest failed: no response data obtained after all retries."
        )
        raise HTTPException(
            status_code=502,
            detail="Drive ingest failed: no response data from Google Drive.",
        )

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
