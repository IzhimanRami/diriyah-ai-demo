export async function ingestDrive(folderId, chatId) {
  const url = `/api/drive/ingest?folderId=${folderId}&chatId=${chatId}`;

  try {
    const resp = await fetch(url, { method: "POST" });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    return await resp.json();
  } catch (err) {
    console.error("Drive ingest failed:", err);
    return { error: err.message };
  }
}
