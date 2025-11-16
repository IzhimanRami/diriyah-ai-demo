# backend/services/ingest.py

import os
import tempfile
from typing import Tuple, Dict, List

from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from pdfminer.high_level import extract_text as pdf_extract

# Name of the Chroma collection (can be overridden with env var)
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "diriyah")

# Use embedded Chroma, persisted on disk inside the container
_client = PersistentClient(path="/app/storage/chroma")
_collection = _client.get_or_create_collection(name=CHROMA_COLLECTION)
_embedder = embedding_functions.DefaultEmbeddingFunction()


def _try_decode(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("latin-1", errors="ignore")


def extract_text_and_metadata(binary: bytes, drive_file: Dict) -> Tuple[str, Dict]:
    """
    Given raw bytes from Google Drive and the file metadata, extract text content
    plus a metadata dict that we will store alongside embeddings.
    """
    name = drive_file.get("name", "").lower()
    mime = drive_file.get("mimeType", "")
    text = ""

    # PDF handling
    if mime == "application/pdf" or name.endswith(".pdf"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(binary)
            tmp.flush()
            text = pdf_extract(tmp.name) or ""

    # Simple text-like files
    elif name.endswith((".txt", ".md", ".csv")):
        text = _try_decode(binary)

    meta = {
        "gdrive_id": drive_file.get("id"),
        "name": drive_file.get("name"),
        "mimeType": mime,
        "webViewLink": drive_file.get("webViewLink"),
        "modifiedTime": drive_file.get("modifiedTime"),
        "source": "gdrive-public",
    }
    return text, meta


def upsert_to_chroma(docs: List[tuple]):
    """
    Upsert a list of (text, metadata) pairs into the global Chroma collection.
    """
    if not docs:
        return

    ids = [d[1]["gdrive_id"] for d in docs]
    documents = [d[0] for d in docs]
    metadatas = [d[1] for d in docs]
    embeddings = _embedder(documents)

    _collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )
