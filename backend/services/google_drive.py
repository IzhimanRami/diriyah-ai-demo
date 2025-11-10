"""
Google Drive access via API key (public-folder, read-only).

This module supports listing and downloading files from a single
publicly shared Google Drive folder using only an API key.
- No OAuth, no Service Account.
- Folder AND items must be shared "Anyone with the link".
- Write operations are NOT supported in API-key mode.

Env vars used:
  GOOGLE_API_KEY            -> your API key
  GOOGLE_PUBLIC_FOLDER_ID   -> the folder ID to read from

Diagnostics helpers:
  drive_stubbed()           -> True when API key/folder are missing
  drive_credentials_available() -> True when API key + folder id exist
  drive_service_error()     -> last error string (if any)

Public functions:
  list_folder_items()       -> list files in the public folder
  download_file_bytes(id)   -> bytes of the file (alt=media), or raises
  upload_to_drive(file_obj) -> returns 'unsupported-api-key-mode'
"""

from __future__ import annotations

import io
import os
from threading import Lock
from typing import Any, Dict, List, Optional

import requests

# ---- Internal state -------------------------------------------------------

_STATE_LOCK = Lock()
_last_service_error: Optional[str] = None
_last_error_source: Optional[str] = None
_api_key_available = False
_folder_id_available = False

# cached env
_API_KEY = os.getenv("GOOGLE_API_KEY") or ""
_FOLDER_ID = os.getenv("GOOGLE_PUBLIC_FOLDER_ID") or ""

with _STATE_LOCK:
    _api_key_available = bool(_API_KEY)
    _folder_id_available = bool(_FOLDER_ID)

# ---- Observability helpers ------------------------------------------------

def drive_credentials_available() -> bool:
    """True when API key and folder id are both present."""
    with _STATE_LOCK:
        return _api_key_available and _folder_id_available


def drive_service_error() -> Optional[str]:
    with _STATE_LOCK:
        return _last_service_error


def drive_stubbed() -> bool:
    """True when we cannot talk to Drive (missing config)."""
    with _STATE_LOCK:
        return not (_api_key_available and _folder_id_available)


def _record_error(message: str, *, source: str) -> None:
    global _last_service_error, _last_error_source
    with _STATE_LOCK:
        _last_service_error = message
        _last_error_source = source


# ---- Public API (read-only) -----------------------------------------------

def list_folder_items() -> List[Dict[str, Any]]:
    """
    List items in the configured public folder.
    Returns a list of dicts: { id, name, mimeType }.
    Falls back to [] on error.
    """
    if drive_stubbed():
        _record_error("Missing GOOGLE_API_KEY or GOOGLE_PUBLIC_FOLDER_ID", source="config")
        return []

    try:
        # Only publicly readable files are returned here.
        params = {
            "q": f"'{_FOLDER_ID}' in parents and trashed=false",
            "fields": "files(id,name,mimeType,iconLink,webViewLink,webContentLink)",
            "pageSize": 200,
            "key": _API_KEY,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        r = requests.get("https://www.googleapis.com/drive/v3/files", params=params, timeout=20)
        r.raise_for_status()
        payload = r.json() or {}
        files = payload.get("files", [])
        if isinstance(files, list):
            return files
        return []
    except Exception as exc:
        _record_error(f"Failed to list folder items: {exc}", source="list")
        return []


def download_file_bytes(file_id: str) -> bytes:
    """
    Download file content (alt=media). The file must be shared publicly,
    or this will fail with 403/404.
    """
    if drive_stubbed():
        raise RuntimeError("Drive not configured (API key / folder id missing).")

    try:
        params = {"alt": "media", "key": _API_KEY}
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        return r.content
    except Exception as exc:
        _record_error(f"Failed to download file {file_id}: {exc}", source="download")
        raise


def upload_to_drive(file_obj: Any) -> str:
    """
    Not supported with API key mode. Return a deterministic token.
    (Keep the signature so existing endpoints don’t break.)
    """
    _record_error("Upload not supported in API-key mode", source="upload")
    return "unsupported-api-key-mode"
