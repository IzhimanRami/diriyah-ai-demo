import React, { useState } from "react";
import { ingestDrive } from "../api/drive";

const DRIVE_FOLDER_ID = "1dOD0ZLvA-iBFBePcZSKJ0zX1q67OyoT9"; // Villa 100 folder for now

export default function DriveIngestButton({ chatId }) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");

  const handleClick = async () => {
    if (!chatId) {
      setStatus("No active chat selected.");
      return;
    }

    setLoading(true);
    setStatus("Starting Google Drive sync…");

    try {
      const result = await ingestDrive(DRIVE_FOLDER_ID, chatId);

      if (result?.error) {
        setStatus(`Error: ${result.error}`);
      } else {
        const count =
          result.fileCount ??
          (Array.isArray(result.files) ? result.files.length : 0);

        setStatus(`Done. Synced ${count} file(s) from Google Drive.`);
      }
    } catch (err) {
      console.error(err);
      setStatus("Unexpected error while syncing Drive.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="drive-ingest-widget">
      <button
        onClick={handleClick}
        disabled={loading}
        className="px-3 py-1.5 text-sm rounded border disabled:opacity-60"
      >
        {loading ? "Syncing…" : "Sync from Google Drive"}
      </button>

      {status && (
        <p className="mt-2 text-xs text-gray-700">
          {status}
        </p>
      )}
    </div>
  );
}
