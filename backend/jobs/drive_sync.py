import asyncio
from typing import List, Dict, Tuple

from backend.api.ingest_utils import extract_text_and_metadata, upsert_to_chroma

try:
    # Optional wrapper around real Drive access
    from backend.services.drive_list import list_drive_files, download_file
except Exception:  # pragma: no cover - defensive
    list_drive_files = None
    download_file = None


async def ingest_folder(folder_id: str) -> Dict[str, str]:
    """
    Ingest all files from a Google Drive folder into Chroma.

    This function is defensive: if Drive access is not configured,
    it will not crash the API – it will just index nothing and
    return a clear message.
    """
    print(f"🔍 Starting Google Drive ingestion for folder: {folder_id}")

    if list_drive_files is None or download_file is None:
        msg = "Drive integration not configured; skipping ingestion."
        print(f"⚠ {msg}")
        return {"status": "skipped", "message": msg}

    try:
        files = await list_drive_files(folder_id)
    except Exception as e:
        msg = f"Failed to list files for folder {folder_id}: {e}"
        print(f"❌ {msg}")
        return {"status": "error", "message": msg}

    print(f"📄 Found {len(files)} files in folder {folder_id}")

    docs: List[Tuple[str, Dict]] = []

    for f in files:
        try:
            binary = await download_file(f["id"])
            text, meta = extract_text_and_metadata(binary, f)

            if text.strip():
                docs.append((text, meta))
                print(f"✔ Indexed: {f.get('name')}")
            else:
                print(f"⚠ No extractable text: {f.get('name')}")

        except Exception as e:
            print(f"❌ Error processing {f.get('name')}: {e}")

    upsert_to_chroma(docs)
    print("🎉 Ingestion done! Indexed documents saved.")

    return {
        "status": "ok",
        "message": f"Ingested {len(docs)} documents from folder {folder_id}",
    }


if __name__ == "__main__":
    import sys

    folder = sys.argv[1] if len(sys.argv) > 1 else None
    if not folder:
        print("❌ Usage: python -m backend.jobs.drive_sync <FOLDER_ID>")
        raise SystemExit(1)

    asyncio.run(ingest_folder(folder))
