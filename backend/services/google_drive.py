"""
Google Drive integration — supports two modes:

1) Service Account mode (OAuth/credentials) — used for private Drive access.
2) Public Folder + API Key mode — read-only listing of files that are shared
   publicly on the web. This works without login and is ideal for demos.

Diagnostics and scan endpoints will prefer Public mode if it is configured.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional, Tuple

import json
import urllib.parse
import urllib.request

# -----------------------------
# Config / Environment
# -----------------------------

_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
_CREDENTIAL_ENV_VAR = "GOOGLE_SERVICE_ACCOUNT"
_DEFAULT_CREDENTIAL_FILE = "service_account.json"

# Public mode (no login)
_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
_GOOGLE_PUBLIC_FOLDER_ID = os.getenv("GOOGLE_PUBLIC_FOLDER_ID", "").strip()

# Internal state locks
_STATE_LOCK = Lock()
_drive_service: Any = None
_service_ready = False
_credentials_available = False
_credential_error: Optional[str] = None
_last_service_error: Optional[str] = None
_last_error_source: Optional[str] = None

# Lazy imports for service-account mode
try:  # pragma: no cover
    from google.oauth2 import service_account  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.http import MediaIoBaseUpload  # type: ignore
except Exception as import_exc:  # pragma: no cover
    service_account = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]
    MediaIoBaseUpload = None  # type: ignore[assignment]
    _IMPORT_ERROR: Optional[BaseException] = import_exc
else:
    _IMPORT_ERROR = None


# -----------------------------
# Helpers
# -----------------------------

def _display_path(path: Path) -> str:
    try:
        return str(path.resolve())
    except FileNotFoundError:
        return str(path.absolute())


def _record_error(message: str, *, source: str) -> None:
    global _last_service_error, _last_error_source, _service_ready, _drive_service
    with _STATE_LOCK:
        _last_service_error = message
        _last_error_source = source
        _service_ready = False
        _drive_service = None


def _update_credentials_state(path: Path) -> None:
    global _credentials_available, _credential_error, _last_service_error, _last_error_source
    exists = path.exists()
    message: Optional[str] = None
    if not exists:
        message = f"Google Drive credentials not found at {_display_path(path)}"
    with _STATE_LOCK:
        _credentials_available = exists
        _credential_error = message
        if exists:
            if _last_error_source == "credentials":
                _last_service_error = None
                _last_error_source = None
        else:
            _last_service_error = message
            _last_error_source = "credentials"
            _service_ready = False


def _credentials_path() -> Path:
    candidate = os.getenv(_CREDENTIAL_ENV_VAR, _DEFAULT_CREDENTIAL_FILE)
    path = Path(candidate).expanduser()
    _update_credentials_state(path)
    return path


# -----------------------------
# Public Mode (API key) helpers
# -----------------------------

def public_mode_enabled() -> bool:
    return bool(_GOOGLE_API_KEY and _GOOGLE_PUBLIC_FOLDER_ID)


def _drive_api(url: str, params: Dict[str, str]) -> Dict[str, Any]:
    """Simple GET using urllib so we don't add new deps."""
    params = {**params, "key": _GOOGLE_API_KEY}  # inject key
    q = urllib.parse.urlencode(params)
    full = f"{url}?{q}"
    with urllib.request.urlopen(full, timeout=20) as resp:  # nosec - public endpoint
        data = resp.read().decode("utf-8")
        return json.loads(data)


def list_public_children(
    folder_id: Optional[str] = None, page_size: int = 50
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    List files in a public folder (shared to 'Anyone with the link').
    Returns (files, next_page_token).
    """
    if not public_mode_enabled():
        return [], None

    parent = folder_id or _GOOGLE_PUBLIC_FOLDER_ID
    q = f"'{parent}' in parents and trashed = false"
    url = "https://www.googleapis.com/drive/v3/files"
    params = {
        "q": q,
        "pageSize": str(page_size),
        "fields": "nextPageToken, files(id,name,mimeType,modifiedTime,webViewLink,iconLink)",
        "supportsAllDrives": "false",
        "includeItemsFromAllDrives": "false",
        "orderBy": "folder,name_natural",
    }
    data = _drive_api(url, params)
    return data.get("files", []), data.get("nextPageToken")


def public_diagnostics() -> Dict[str, Any]:
    """
    Return a health snapshot for public mode.
    """
    diag: Dict[str, Any] = {
        "mode": "public",
        "configured": public_mode_enabled(),
        "folder_id": _GOOGLE_PUBLIC_FOLDER_ID or None,
        "can_list": False,
        "error": None,
        "sample": [],
    }
    if not public_mode_enabled():
        diag["error"] = "Public mode is not configured (missing GOOGLE_API_KEY or GOOGLE_PUBLIC_FOLDER_ID)."
        return diag

    try:
        files, _ = list_public_children(page_size=5)
        diag["can_list"] = True
        diag["sample"] = files
    except Exception as exc:  # pragma: no cover
        diag["error"] = f"Listing failed: {exc!s}"
    return diag


# -----------------------------
# Service-account mode (private)
# -----------------------------

def get_drive_service() -> Any:
    with _STATE_LOCK:
        if _service_ready and _drive_service is not None:
            return _drive_service

    if _IMPORT_ERROR is not None or service_account is None or build is None:
        message = f"Google Drive client libraries unavailable: {_IMPORT_ERROR!s}"
        _record_error(message, source="import")
        raise RuntimeError(message) from _IMPORT_ERROR

    credentials_path = _credentials_path()
    with _STATE_LOCK:
        credentials_ok = _credentials_available
        credential_problem = _credential_error
    if not credentials_ok:
        raise RuntimeError(credential_problem or "Google Drive credentials missing")

    try:
        credentials = service_account.Credentials.from_service_account_file(  # type: ignore[union-attr]
            str(credentials_path), scopes=_DRIVE_SCOPES
        )
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    except Exception as exc:  # pragma: no cover
        message = f"Failed to initialise Google Drive service: {exc}"
        _record_error(message, source="initialise")
        raise RuntimeError(message) from exc

    with _STATE_LOCK:
        global _drive_service, _service_ready, _last_service_error, _last_error_source
        _drive_service = service
        _service_ready = True
        if _last_error_source != "credentials":
            _last_service_error = None
            _last_error_source = None
    return service


def upload_to_drive(file_obj: Any) -> str:
    """
    Upload uses service-account mode only. In public mode this returns a stubbed ID
    because public+API key cannot write.
    """
    if public_mode_enabled() or MediaIoBaseUpload is None:
        return "stubbed-upload-id"

    try:
        service = get_drive_service()
    except RuntimeError:
        return "stubbed-upload-id"

    if hasattr(file_obj, "file"):
        content = file_obj.file.read()
        file_obj.file.seek(0)
        filename = getattr(file_obj, "filename", "upload.bin")
        content_type = getattr(file_obj, "content_type", "application/octet-stream")
    else:
        content = getattr(file_obj, "read", lambda: b"")()
        filename = getattr(file_obj, "name", "upload.bin")
        content_type = getattr(file_obj, "content_type", "application/octet-stream")

    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=content_type, resumable=False)
    metadata: Dict[str, Any] = {"name": filename}

    try:
        response = (
            service.files()
            .create(body=metadata, media_body=media, fields="id")
            .execute()
        )
    except Exception:
        return "stubbed-upload-id"

    return str(response.get("id", "stubbed-upload-id"))
