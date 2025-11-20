import React, { useState } from "react";
import { ingestDrive } from "../api/drive";

const DRIVE_FOLDER_ID = "1dOD0ZLvA-iBFBePcZSKJ0zX1q67OyoT9";
const CHAT_ID = "villa-ops"; // the same you used in the console test

export default function DriveIngestButton() {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");

  const handleClick = async () => {
    setLoading(true);
    setStatus("Starting Drive sync…");

    try {
      const result = await ingestDrive(DRIVE_FOLDER_ID, CHAT_ID);

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
    <div className="p-6 rounded-xl border border-gray-200 bg-white shadow-sm">
      <h2 className="text-lg font-semibold mb-2">Google Drive sync</h2>
      <p className="text-sm text-gray-600 mb-4">
        Click the button to pull files from the project Drive folder into this chat.
      </p>

      <button
        onClick={handleClick}
        disabled={loading}
        className="px-4 py-2 rounded-lg border text-sm font-medium
                   disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {loading ? "Syncing…" : "Sync from Google Drive"}
      </button>

      {status && (
        <p className="mt-3 text-sm text-gray-700">
          {status}
        </p>
      )}
    </div>
  );
}
