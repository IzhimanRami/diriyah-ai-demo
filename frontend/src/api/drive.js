// frontend/src/api/drive.js

export async function ingestDrive(folderId, chatId) {
  // Call the FastAPI endpoint that talks to Google Drive
  const url = `/api/drive/ingest?folderId=${encodeURIComponent(
    folderId,
  )}&chatId=${encodeURIComponent(chatId)}`;

  try {
    // IMPORTANT: use GET (no method option).
    // We already confirmed this works in the browser & devtools.
    const resp = await fetch(url);

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    // Backend returns JSON like:
    // { folderId, chatId, fileCount, files: [...] }
    return await resp.json();
  } catch (err) {
    console.error("Drive ingest failed:", err);
    return { error: err.message || "Unknown error" };
  }
}
