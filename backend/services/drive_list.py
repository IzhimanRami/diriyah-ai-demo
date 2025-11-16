import io
import os
from typing import List, Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Read-only access – enough to list & download files
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _get_service():
    """
    Build a Google Drive service client using the same
    service account JSON you configured on Render.

    Make sure GOOGLE_APPLICATION_CREDENTIALS is set in Render
    to the path of your service account JSON file.
    """
    credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_file:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is not set")

    creds = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=SCOPES,
    )

    # cache_discovery=False avoids some warnings in serverless environments
    return build("drive", "v3", credentials=creds, cache_discovery=False)


async def list_drive_files(folder_id: str) -> List[Dict]:
    """
    Return all non-trashed files inside the given folder.

    Each item has at least:
    - id
    - name
    - mimeType
    - webViewLink
    - modifiedTime
    """
    service = _get_service()

    query = f"'{folder_id}' in parents and trashed = false"

    results = service.files().list(
        q=query,
        pageSize=1000,
        fields="files(id, name, mimeType, webViewLink, modifiedTime)",
    ).execute()

    files = results.get("files", [])
    return files


async def download_file(file_id: str) -> bytes:
    """
    Download a file's binary content from Google Drive.
    Returns raw bytes that we pass to pdfminer / text decoder.
    """
    service = _get_service()

    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    fh.seek(0)
    return fh.read()
