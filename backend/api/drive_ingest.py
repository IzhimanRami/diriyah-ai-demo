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
# Config & env
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAY_SEC = 2  # seconds between retries

# IMPORTANT: strip whitespace so a leading/trailing space in Render env
# does not break the key.
_GOOGLE_API_KEY = os.environ.get("GOOGLE_DRIVE_API_KEY", "").strip()

if not _GOOGLE_API_KEY:
    logger.warning(
        "GOOGLE_DRIVE_API_KEY env var is not set or is empty. "
        "Drive ingest endpoint will return 500 until this is configured."
    )

_DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder. Uses a retry loop for robustness.
    """

    if not _GOOGLE_API_KEY:
        # Fail per-request instead of crashing app startup
        raise HTTPException(
            status_code=500,
            detail="Drive ingest misconfigured: GOOGLE_DRIVE_API_KEY env var is not set",
        )

    # EXACTLY the query that works in your browser:
    # query_str = f"'{folder_id}' in parents and trashed=false"
query_str = f"'{folder_id}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder'"
    params = {
        "q": query_str,
        "key": _GOOGLE_API_KEY,
        # Keep it simple & identical to your working test
        "fields": "files(id,name,mimeType)",
        # If you want all-drives support later, we can add:
        # "supportsAllDrives": "true",
        # "includeItemsFromAllDrives": "true",
    }

    url = _DRIVE_LIST_URL + "?" + urllib.parse.urlencode(params)

    # Log for sanity-checking
    logger.info(
        "Drive ingest: calling Google Drive API for folder %s", folder_id
    )
    logger.debug(
        "Drive ingest URL (sanitised): %s", url.replace(_GOOGLE_API_KEY, "***KEY***")
    )
    logger.debug("Drive API key length: %d", len(_GOOGLE_API_KEY))

    raw: bytes | None = None

    # ---------------- Retry loop ----------------
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                raw = resp.read()
            logger.info("Drive API call successful on attempt %d", attempt)
            break

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
                    "All %d retries failed for folder %s", MAX_RETRIES, folder_id
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
                    detail=f"Drive ingest failed after {MAX_RETRIES} attempts: {exc}",
                ) from exc

            time.sleep(RETRY_DELAY_SEC)
    # -------------------------------------------

    if raw is None:
        logger.error("Failed to obtain response data from Google Drive after retries")
        raise HTTPException(
            status_code=502,
            detail="Drive ingest failed: No data returned from Google Drive.",
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
      * Fetch the file list via API key
      * Return them as JSON

    Later:
      * Download + embed + store in vector DB
      * Link embeddings to the given chat_id (e.g. "villa-ops")
    """
    logger.info("Starting ingest for folder %s (chat_id=%s)", folder_id, chat_id)

    files = _fetch_drive_files_via_api_key(folder_id)

    return {
        "folderId": folder_id,
        "chatId": chat_id,
        "fileCount": len(files),
        "files": files,
    }
