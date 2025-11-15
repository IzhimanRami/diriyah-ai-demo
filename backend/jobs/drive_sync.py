import logging
import os
from typing import Dict, List

import requests

from backend.services.ingest import extract_text_and_metadata, upsert_to_chroma

log = logging.getLogger(__name__)

# Env vars you need to set in Render
GDRIVE_API_KEY = os.getenv("GDRIVE_API_KEY") or os.getenv("GOOGLE_API_KEY")
GDRIVE_PARENT_ID = os.getenv("GDRIVE_PARENT_ID")

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_FILE_CONTENT_URL = "https://www.googleapis.com/drive/v3/files/{file_id}"


def _list_children(folder_id: str) -> List[Dict]:
    """List direct children of a folder."""
    if not GDRIVE_API_KEY:
        raise RuntimeError("GDRIVE_API_KEY (or GOOGLE_API_KEY) is not set")

    files: List[Dict] = []
    page_token: str | None = None

    while True:
        params = {
            "key": GDRIVE_API_KEY,
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(DRIVE_FILES_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        files.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return files


def _walk_tree(root_folder_id: str) -> List[Dict]:
    """
    Recursively walk the Google Drive folder tree starting from root_folder_id.
    Returns *files only* (PDF/TXT/CSV/etc.), not folders.
    """
    stack = [root_folder_id]
    all_files: List[Dict] = []

    while stack:
        current = stack.pop()
        children = _list_children(current)

        for f in children:
            mime = f.get("mimeType") or ""
            if mime == "application/vnd.google-apps.folder":
                # Dive into sub-folder
                stack.append(f["id"])
            else:
                all_files.append(f)

    return all_files


def _download_file(file_id: str) -> bytes:
    """Download raw bytes of a Drive file by id."""
    if not GDRIVE_API_KEY:
        raise RuntimeError("GDRIVE_API_KEY (or GOOGLE_API_KEY) is not set")

    params = {"alt": "media", "key": GDRIVE_API_KEY}
    url = DRIVE_FILE_CONTENT_URL.format(file_id=file_id)

    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.content


def sync_folder(folder_id: str) -> Dict[str, int]:
    """
    Main sync routine:
    - Walk the Drive tree from folder_id
    - Download each file
    - Extract text + metadata using ingest.py
    - Upsert embeddings into Chroma
    """
    log.info("Starting Drive sync for folder %s", folder_id)
    files = _walk_tree(folder_id)
    log.info("Found %d files under folder %s", len(files), folder_id)

    batch: List[tuple] = []
    indexed = 0
    skipped = 0

    for f in files:
        file_id = f.get("id")
        name = f.get("name")

        try:
            binary = _download_file(file_id)
            text, meta = extract_text_and_metadata(binary, f)

            if text and text.strip():
                batch.append((text, meta))
                indexed += 1

                # Upsert in batches for performance
                if len(batch) >= 32:
                    upsert_to_chroma(batch)
                    batch = []
            else:
                skipped += 1
                log.info("Skipping empty/unsupported file: %s (%s)", name, file_id)

        except Exception as exc:  # pragma: no cover - defensive
            skipped += 1
            log.exception("Failed to process file %s (%s): %s", name, file_id, exc)

    # Flush any remaining docs
    if batch:
        upsert_to_chroma(batch)

    stats = {
        "total_files": len(files),
        "indexed_files": indexed,
        "skipped_files": skipped,
    }
    log.info("Drive sync finished: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not GDRIVE_PARENT_ID:
        raise SystemExit("GDRIVE_PARENT_ID is not set")

    result = sync_folder(GDRIVE_PARENT_ID)
    print("Sync completed:", result)
