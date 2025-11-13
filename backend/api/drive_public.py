import os, requests
from typing import List, Dict
from fastapi import APIRouter, HTTPException, Query
from .ingest_utils import extract_text_and_metadata, upsert_to_chroma

router = APIRouter(prefix="/drive", tags=["drive"])

GDRIVE_API_KEY = os.getenv("GDRIVE_API_KEY")
BASE = "https://www.googleapis.com/drive/v3"

def _files_list(folder_id: str) -> List[Dict]:
    if not GDRIVE_API_KEY:
        raise HTTPException(status_code=500, detail="GDRIVE_API_KEY not set")
    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "key": GDRIVE_API_KEY,
        "pageSize": 1000,
        "fields": "files(id,name,mimeType,webViewLink,size,modifiedTime)"
    }
    r = requests.get(f"{BASE}/files", params=params, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text)
    return r.json().get("files", [])

def _download_file(file_id: str, mime: str) -> bytes:
    google_types = {
        "application/vnd.google-apps.document": "application/pdf",
        "application/vnd.google-apps.spreadsheet": "application/pdf",
        "application/vnd.google-apps.presentation": "application/pdf",
    }
    if mime in google_types:
        url = f"{BASE}/files/{file_id}/export"
        params = {"mimeType": google_types[mime], "key": GDRIVE_API_KEY}
    else:
        url = f"{BASE}/files/{file_id}?alt=media"
        params = {"key": GDRIVE_API_KEY}
    r = requests.get(url, params=params, timeout=120)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text)
    return r.content

@router.get("/list")
def list_public(folderId: str = Query(..., alias="folderId")):
    return {"files": _files_list(folderId)}

@router.post("/ingest")
def ingest(folderId: str | None = Query(None, alias="folderId")):
    folder_id = folderId or os.getenv("GDRIVE_FOLDER_ID_MASTER")
    if not folder_id:
        raise HTTPException(status_code=400, detail="folderId missing")
    files = _files_list(folder_id)
    docs = []
    for f in files:
        try:
            content = _download_file(f["id"], f.get("mimeType", ""))
            text, meta = extract_text_and_metadata(content, f)
            if text.strip():
                docs.append((text, meta))
        except Exception as e:
            print("Ingest error:", f.get("name"), e)
            continue
    upsert_to_chroma(docs)
    return {"ingested": len(docs)}
