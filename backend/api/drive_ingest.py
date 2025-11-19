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

# --- Configuration for Retry Logic ---
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2 # Wait 2 seconds before retrying network calls
# -------------------------------------

# ---------------------------------------------------------------------------
# Google Drive API helper using API KEY (no service account)
# ---------------------------------------------------------------------------

_GOOGLE_API_KEY = os.environ.get("GOOGLE_DRIVE_API_KEY")

if not _GOOGLE_API_KEY:
    logger.warning(
        "GOOGLE_DRIVE_API_KEY env var is not set. "
        "Drive ingest will return 500 until this is configured."
    )

_DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"


def _fetch_drive_files_via_api_key(folder_id: str) -> List[Dict[str, Any]]:
    """
    Call the public Google Drive v3 API using an API key, listing all files
    in the given folder, with a retry mechanism for robustness.
    """

    if not _GOOGLE_API_KEY:
        # Now we fail per-request with a clean 500 instead of breaking startup.
        raise HTTPException(
            status_code=500,
            detail="Drive ingest misconfigured: GOOGLE_DRIVE_API_KEY env var is not set",
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
    
    raw = None  # Variable to hold the successful response data

    # --- Start Retry Loop ---
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "Drive ingest: calling Google Drive API for folder %s (Attempt %d/%d)",
            folder_id,
            attempt,
            MAX_RETRIES,
        )
        logger.debug("Drive ingest URL: %s", url)

        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                raw = resp.read()
            
            # Success! Break the retry loop.
            logger.info("Drive API call successful on attempt %d.", attempt)
            break 
            
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            logger.warning(
                "Google Drive API HTTP error %s on attempt %d: %s",
                exc.code,
                attempt,
                body,
            )
            
            # If it's the final attempt, raise the error.
            if attempt == MAX_RETRIES:
                logger.error("All %d retries failed for folder %s.", MAX_RETRIES, folder_id)
                raise HTTPException(
                    status_code=502,
                    detail=f"Drive ingest failed after {MAX_RETRIES} attempts: Google Drive API HTTP {exc.code}: {body}",
                ) from exc
            
            # Wait before the next attempt
            time.sleep(RETRY_DELAY_SEC)
            
        except Exception as exc:  # noqa: BLE001 (For network/unknown errors)
            logger.exception("Network/unknown error calling Google Drive API on attempt %d.", attempt)
            
            if attempt == MAX_RETRIES:
                raise HTTPException(
                    status_code=502,
                    detail=f"Drive ingest failed after {MAX_RETRIES} attempts: {exc}",
                ) from exc
            
            time.sleep(RETRY_DELAY_SEC)
    
    # --- End Retry Loop ---

    if raw is None:
        # Should not happen if exceptions are raised correctly, but serves as a final safeguard.
        logger.error("Failed to obtain raw response data after all retries.")
        raise HTTPException(status_code=502, detail="Drive ingest failed: Could not retrieve data from Google Drive.")

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

    # This call now includes the retry mechanism
    files = _fetch_drive_files_via_api_key(folder_id)

    return {
        "folderId": folder_id,
        "chatId": chat_id,
        "fileCount": len(files),
        "files": files,
    }
