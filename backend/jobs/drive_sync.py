import asyncio
from backend.services.drive_list import list_drive_files, download_file
from backend.services.ingest import extract_text_and_metadata, upsert_to_chroma


async def ingest_folder(folder_id: str):
    print(f"🔍 Starting Google Drive ingestion for folder: {folder_id}")

    files = await list_drive_files(folder_id)
    print(f"📄 Found {len(files)} files")

    docs = []

    for f in files:
        try:
            binary = await download_file(f["id"])
            text, meta = extract_text_and_metadata(binary, f)

            if text.strip():
                docs.append((text, meta))
                print(f"✔ Indexed: {f['name']}")
            else:
                print(f"⚠ No extractable text: {f['name']}")

        except Exception as e:
            print(f"❌ Error processing {f['name']}: {e}")

    upsert_to_chroma(docs)
    print("🎉 Ingestion done! Indexed documents saved.")


if __name__ == "__main__":
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else None

    if not folder:
        print("❌ Usage: python -m backend.jobs.drive_sync <FOLDER_ID>")
        exit(1)

    asyncio.run(ingest_folder(folder))
