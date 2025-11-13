import os, tempfile
from typing import Tuple, Dict, List
from chromadb import HttpClient
from chromadb.utils import embedding_functions
from pdfminer.high_level import extract_text as pdf_extract

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "diriyah")

_client = HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
_collection = _client.get_or_create_collection(CHROMA_COLLECTION)
_embedder = embedding_functions.DefaultEmbeddingFunction()

def _try_decode(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("latin-1", errors="ignore")

def extract_text_and_metadata(binary: bytes, drive_file: Dict) -> Tuple[str, Dict]:
    name = drive_file.get("name", "").lower()
    mime = drive_file.get("mimeType", "")
    text = ""

    if mime == "application/pdf" or name.endswith(".pdf"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(binary)
            tmp.flush()
            text = pdf_extract(tmp.name) or ""
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
    if not docs:
        return
    ids = [d[1]["gdrive_id"] for d in docs]
    documents = [d[0] for d in docs]
    metadatas = [d[1] for d in docs]
    embeddings = _embedder(documents)
    _collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
