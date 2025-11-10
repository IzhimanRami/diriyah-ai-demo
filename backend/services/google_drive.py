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
  diagnostics()                 -> dict for /api/drive/diagnostics
  drive_stubbed()               -> True when API key/folder are missing
  drive_credentials_available() -> True when API key + folder id exist
  drive_service_error()         -> last error string (if any)

Public functions:
  list_folder_items(...)    -> list files (paged) from the public folder
  download_file_bytes(id)   -> bytes of the file (alt=media), or raises
  upload_to_drive(file_obj) -> returns 'unsupported-api-key-mode'
"""

from __future__ import annotations

import os
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---- Internal state -------------------------------------------------------

_STATE_LOCK = Lock()
_last_service_error: Optional[str] = None
_last_error_source: Optional[str] = None

# Cached env
_API_KEY = (os.getenv("GOOGLE_API_KEY") or "").strip()
_FOLDER_ID = (os.getenv("GOOGLE_PUBLIC_FOLDER_ID") or "").strip()

# ---- Observability helpers ------------------------------------------------

def drive_credentials_available() -> bool:
    """True when API key and folder id are both present."""
    return bool(_API_KEY and _FOLDER_ID)


def drive_service_error() -> Optional[str]:
    with _STATE_LOCK:
        return _last_service_error


def drive_stubbed() -> bool:
    """True when we cannot talk to Drive (missing config)."""
    return not drive_credentials_available()


def _record_error(message: str, *, source: str) -> None:
    global _last_service_error, _last_error_source
    with _STATE_LOCK:
        _last_service_error = message
        _last_error_source = source


def _short(s: Optional[str], keep: int = 8) -> Optional[str]:
    if not s:
        return None
    return s[:keep] + "…" if len(s) > keep else s


def _fallback_webview_link(file_id: str) -> str:
    # Works for publicly shared files
    return f"https://drive.google.com/file/d/{file_id}/view"


# ---- Diagnostics (for /api/drive/diagnostics) -----------------------------

def diagnostics() -> Dict[str, Any]:
    """
    Returns a compact status payload expected by /api/drive/diagnostics.
    """
    status = {
        "mode": "api-key-public-folder-readonly",
        "stubbed": drive_stubbed(),
        "has_api_key": bool(_API_KEY),
        "has_public_folder_id": bool(_FOLDER_ID),
        "public_folder_id": _short(_FOLDER_ID),
        "last_error": drive_service_error(),
    }
    return status


# ---- Public API (read-only) -----------------------------------------------

def list_folder_items(
    page_token: Optional[str] = None,
    page_size: int = 100,
) -> Dict[str, Any]:
    """
    List items in the configured public folder (paged).
    Returns a dict:
      {
        "files": [{ id, name, mimeType, size?, modifiedTime?, webViewLink, iconLink }],
        "nextPageToken": "...?" | None
      }
    Falls back to {"files": [], "nextPageToken": None} on error.
    """
    if drive_stubbed():
        _record_error("Missing GOOGLE_API_KEY or GOOGLE_PUBLIC_FOLDER_ID", source="config")
        return {"files": [], "nextPageToken": None}

    try:
        params = {
            "q": f"'{_FOLDER_ID}' in parents and trashed=false",
            "fields": (
                "nextPageToken,"
                "files(id,name,mimeType,size,modifiedTime,iconLink,webViewLink)"
            ),
            "pageSize": max(1, min(int(page_size), 1000)),
            "key": _API_KEY,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if page_token:
            params["pageToken"] = page_token

        r = requests.get("https://www.googleapis.com/drive/v3/files", params=params, timeout=20)
        r.raise_for_status()
        data = r.json() or {}
        files = data.get("files", []) or []

        # Ensure each file has a webViewLink (fallback if missing)
        for f in files:
            if f.get("id") and not f.get("webViewLink"):
                f["webViewLink"] = _fallback_webview_link(f["id"])

        return {
            "files": files,
            "nextPageToken": data.get("nextPageToken"),
        }
    except Exception as exc:
        _record_error(f"Failed to list folder items: {exc}", source="list")
        return {"files": [], "nextPageToken": None}


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


def upload_to_drive(_file_obj: Any) -> str:
    """
    Not supported with API key mode. Return a deterministic token.
    (Keep the signature so existing endpoints don’t break.)
    """
    _record_error("Upload not supported in API-key mode", source="upload")
    return "unsupported-api-key-mode"
