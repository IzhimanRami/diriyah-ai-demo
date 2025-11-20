import React, { useState } from "react";
import { ingestDrive } from "../api/drive";

export default function DriveIngestButton() {
  const [status, setStatus] = useState(null);

  async function handleClick() {
    setStatus("Syncing…");

    const result = await ingestDrive(
      "1dOD0ZLvA-iBfBEpCzSKJ0zX1q67OyoT9",  // <<< your folderId
      "villa-ops"                          // <<< your chatId
    );

    setStatus(JSON.stringify(result, null, 2));
  }

  return (
    <div style={{ marginTop: "20px" }}>
      <button
        onClick={handleClick}
        style={{
          padding: "10px 18px",
          background: "#4a5",
          color: "#fff",
          borderRadius: "6px",
          border: "none",
          cursor: "pointer"
        }}
      >
        Sync Google Drive Files
      </button>

      {status && (
        <pre
          style={{
            background: "#eee",
            padding: "10px",
            marginTop: "10px",
            fontSize: "12px",
            whiteSpace: "pre-wrap"
          }}
        >
          {status}
        </pre>
      )}
    </div>
  );
}
