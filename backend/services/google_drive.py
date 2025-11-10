"""Utilities and stubs for interacting with Google Drive.

This module provides a very small abstraction layer that the rest of the
application interacts with. When the real Google client libraries are
available we attempt to build a Drive service using the configured service
account file. When the libraries or credentials are unavailable we fall back
to deterministic stubbed responses that are convenient for local development
and unit tests.

The public helpers intentionally track a bit of internal state so that
observability surfaces (notably the ``/health`` endpoint) can show whether the
service is running in stubbed mode as well as the most recent error that
prevented the real integration from initialising.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

# --- Optional Google client imports ------------------------------------------
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

# --- Config ------------------------------------------------------------------
_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
_CREDENTIAL_ENV_VAR = "GOOGLE_SERVICE_ACCOUNT"
_DEFAULT_CREDENTIAL_FILE = "service_account.json"

# --- Module state ------------------------------------------------------------
_STATE_LOCK = Lock()
_drive_service: Any = None
_service_ready = False
_credentials_available = False
_credential_error: Optional[str] = None
_last_service_error: Optional[str] = None
_last_error_source: Optional[str] = None

# --- Stub data ---------------------------------------------------------------
_STUB_FOLDERS: List[Dict[str, str]] = [
    {"id": "stub-folder-gateway", "name": "Gateway Villas Phase 1", "mimeType": "application/vnd.google-apps.folder"},
    {"id": "stub-folder-towers", "name": "Downtown Towers", "mimeType": "application/vnd.google-apps.folder"},
    {"id": "stub-folder-infra", "name": "Infrastructure Package", "mimeType": "application/vnd.google-apps.folder"},
]

# --- Helpers -----------------------------------------------------------------
def _display_path(path: Path) -> str:
    """Return a friendly representation of ``path`` for error messages."""
    try:
        return str(path.resolve())
    except FileNotFoundError:  # pragma: no cover
        return str(path.absolute())


def _record_error(message: str, *, source: str) -> None:
    """Persist ``message`` as the latest Drive integration error."""
    global _last_service_error, _last_error_source, _service_ready, _drive_service
    with _STATE_LOCK:
        _last_service_error = message
        _last_error_source = source
        _service_ready = False
        _drive_service = None


def _update_credentials_state(path: Path) -> None:
    """Update bookkeeping related to credential availability."""
    global _credentials_available, _credential_error, _last_service_error, _last_error_source, _service_ready, _drive_service
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
            _drive_service = None


def _credentials_path() -> Path:
    """Return the configured path to the service account file."""
    candidate = os.getenv(_CREDENTIAL_ENV_VAR, _DEFAULT_CREDENTIAL_FILE)
    path = Path(candidate).expanduser()
    _update_credentials_state(path)
    return path


# --- Public state accessors ---------------------------------------------------
def drive_credentials_available() -> bool:
    """Return True when the configured credentials file exists."""
    _credentials_path()
    with _STATE_LOCK:
        return _credentials_available


def drive_service_error() -> Optional[str]:
    """Return the most recent error encountered initialising the service."""
    with _STATE_LOCK:
        return _last_service_error


def drive_stubbed() -> bool:
    """Return True when the Drive integration is operating in stub mode."""
    with _STATE_LOCK:
        return not (_service_ready and _credentials_available)


# --- Service lifecycle --------------------------------------------------------
def _initialise_service() -> Any:
    """Construct and cache a Google Drive service instance."""
    global _drive_service, _service_ready, _last_service_error, _last_error_source

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
            str(credentials_path),
            scopes=_DRIVE_SCOPES,
        )
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    except Exception as exc:  # pragma: no cover
        message = f"Failed to initialise Google Drive service: {exc}"
        _record_error(message, source="initialise")
        raise RuntimeError(message) from exc

    with _STATE_LOCK:
        _drive_service = service
        _service_ready = True
        if _last_error_source != "credentials":
            _last_service_error = None
            _last_error_source = None
    return service


def get_drive_service() -> Any:
    """Return a Google Drive service or raise RuntimeError on failure."""
    with _STATE_LOCK:
        if _service_ready and _drive_service is not None:
            return _drive_service
    return _initialise_service()


# --- Public operations --------------------------------------------------------
def list_project_folders() -> List[Dict[str, Any]]:
    """List folders from Google Drive, falling back to stub data on failure."""
    try:
        service = get_drive_service()
    except RuntimeError:
        return list(_STUB_FOLDERS)

    try:
        response = (
            service.files()
            .list(
                q="mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id,name,mimeType)",
                pageSize=200,
            )
            .execute()
        )
    except Exception as exc:  # pragma: no cover
        _record_error(f"Failed to list Google Drive folders: {exc}", source="list")
        return list(_STUB_FOLDERS)

    files = response.get("files", [])
    if isinstance(files, Iterable):
        return list(files)
    return list(_STUB_FOLDERS)


def upload_to_drive(file_obj: Any) -> str:
    """Upload a file-like object to Drive or return a stub identifier when stubbed."""
    try:
        service = get_drive_service()
    except RuntimeError:
        return "stubbed-upload-id"

    if MediaIoBaseUpload is None:
        return "stubbed-upload-id"

    # Starlette/FastAPI UploadFile or plain file-like
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
        response = service.files().create(body=metadata, media_body=media, fields="id").execute()
    except Exception as exc:  # pragma: no cover
        _record_error(f"Failed to upload file to Google Drive: {exc}", source="upload")
        return "stubbed-upload-id"

    return str(response.get("id", "stubbed-upload-id"))


# --- Compatibility stub for routers expecting OAuth user flow -----------------
def oauth_flow(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """
    Compatibility stub.

    Your app imports `oauth_flow` from this module (e.g., in `backend/api/drive.py`),
    but this service uses a Service Account and does not require a user OAuth flow.
    This stub keeps the API stable and allows the app to boot.
    """
    return {
        "enabled": False,
        "mode": "service_account",
        "message": "OAuth flow not configured – using service account credentials.",
    }
