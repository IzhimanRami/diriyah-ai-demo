# backend/services/drive_service.py

import os
from typing import List, Dict

import requests

GDRIVE_API_KEY = os.getenv("GDRIVE_API_KEY")
BASE_URL = "https://www.googleapis.com/drive/v3/files"


def _ensure_api_key() -> str:
    if not GDRIVE_API_KEY:
        raise RuntimeError("GDRIVE_API_KEY env var is missing")
    return GDRIVE_API_KEY


def list_files_in_folder(folder_id: str) -> List[Dict]:
    """
    List files in a public Google Drive folder using an API key.
    """
    api_key = _ensure_api_key()

    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
        "key": api_key,
    }

    resp = requests.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    return data.get("files", [])


def download_file(file_id: str) -> bytes:
    """
    Download the raw bytes of a file using the same API key.
    """
    api_key = _ensure_api_key()

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    params = {"alt": "media", "key": api_key}

    resp = requests.get(url, params=params, stream=True, timeout=60)
    resp.raise_for_status()
    return resp.content
