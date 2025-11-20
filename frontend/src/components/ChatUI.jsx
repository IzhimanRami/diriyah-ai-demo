import React, { useMemo, useRef, useState } from "react";
import DriveIngestButton from "./DriveIngestButton";

function ContextIcon({ type, isActive }) {
  let paths;

  switch (type) {
    case "tasks":
      paths = (
        <>
          <path d="M7 7h10" />
          <path d="M7 12h10" />
          <path d="M7 17h6" />
          <path d="M5 5l2 2" />
        </>
      );
      break;
    case "files":
      paths = (
        <>
          <path d="M8 4h5l5 5v11H8z" />
          <path d="M13 4v5h5" />
        </>
      );
      break;
    case "activity":
      paths = (
        <>
          <path d="M4 13l4-4 4 6 4-3 4 4" />
          <path d="M4 19h16" />
        </>
      );
      break;
    case "summary":
    default:
      paths = (
        <>
          <path d="M6 5h12" />
          <path d="M6 10h12" />
          <path d="M6 15h8" />
          <path d="M6 20h6" />
        </>
      );
      break;
  }

  return (
    <svg
      className={`icon__svg ${isActive ? "icon__svg--active" : ""}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="presentation"
      aria-hidden="true"
    >
      {paths}
    </svg>
  );
}

function ComposerIcon({ name, isActive }) {
  let paths;

  switch (name) {
    case "paperclip":
      paths = (
        <>
          <path d="M8 8l6-6a4 4 0 1 1 5.66 5.66L11 16a3 3 0 1 1-4.24-4.24l8.49-8.49" />
        </>
      );
      break;
    case "camera":
      paths = (
        <>
          <rect x="4" y="7" width="16" height="13" rx="2" />
          <path d="M9 4h6l2 3" />
          <circle cx="12" cy="14" r="3.5" />
        </>
      );
      break;
    case "microphone":
      paths = (
        <>
          <rect x="10" y="4" width="4" height="9" rx="2" />
          <path d="M8 11a4 4 0 0 0 8 0" />
          <path d="M12 19v-4" />
          <path d="M9 19h6" />
        </>
      );
      break;
    default:
      paths = null;
  }

  return (
    <svg
      className={`icon__svg ${isActive ? "icon__svg--active" : ""}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="presentation"
      aria-hidden="true"
    >
      {paths}
    </svg>
  );
}

export default function ChatUI({
  project,
  conversation,
  isContextPanelOpen,
  onToggleContextPanel,
  onSubmitMessage,
  onUploadAttachment,
  onToggleMicrophone,
  microphoneEnabled,
  onMessageAction,
}) {
  const [composerValue, setComposerValue] = useState("");
  const [activeTab, setActiveTab] = useState("summary");
  const fileInputRef = useRef(null);

  const contextTabs = useMemo(
    () => [
      { id: "summary", label: "Summary", items: conversation.context.summary },
      { id: "tasks", label: "Tasks", items: conversation.context.tasks },
      { id: "files", label: "Files", items: conversation.context.files },
      { id: "activity", label: "Activity", items: conversation.context.activity },
    ],
    [conversation.context],
  );

  const activeContextTab = useMemo(
    () => contextTabs.find((tab) => tab.id === activeTab) ?? contextTabs[0],
    [activeTab, contextTabs],
  );

  const handleAttachmentClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event) => {
    const fileName = event.target.files?.[0]?.name;
    if (fileName) {
      onUploadAttachment?.(conversation.id, fileName);
      setComposerValue((previous) => (previous ? `${previous}\nAttached: ${fileName}` : `Attached: ${fileName}`));
    }
    if (event.target) {
      event.target.value = "";
    }
  };

  const handleMicToggle = () => {
    onToggleMicrophone?.();
  };

  const handleComposerChange = (event) => {
    setComposerValue(event.target.value);
  };

  const handleComposerSubmit = (event) => {
    event.preventDefault();
    const trimmed = composerValue.trim();
    if (trimmed) {
      onSubmitMessage?.(conversation.id, trimmed);
      setComposerValue("");
    }
  };

  return (
    <>
      <div className="chat" role="main">
        <header className="chat__header">
          <div>
            <p className="chat__project-name">{conversation.title}</p>
            <p className="chat__project-meta">
              {project.name} • {conversation.lastActivity}
            </p>
          </div>
          <div className="chat__header-actions">
            <span
              className={`chat__status ${conversation.isLive ? "chat__status--connected" : ""}`}
              aria-label={conversation.isLive ? "Connected" : "Offline"}
            />
            <button
              type="button"
              className="chat__context-toggle"
              onClick={onToggleContextPanel}
              aria-pressed={isContextPanelOpen}
            >
              {isContextPanelOpen ? "Hide context" : "Show context"}
            </button>
          </div>
        </header>

        <div className="chat__window">
          {conversation.timeline.map((entry) => (
            <section key={entry.id} className="chat__day-group" aria-label={entry.label}>
              <div className="chat__date-divider">{entry.label}</div>
              {entry.messages.map((message) => (
                <article
                  key={message.id}
                  className={`chat__msg ${message.role === "user" ? "chat__msg--user" : ""}`}
                >
                  <div className="chat__bubble">
                    <p>{message.body}</p>
                  </div>
                  <footer className="chat__meta">
                    <span>{message.author}</span>
                    <span>{message.timestamp}</span>
                    {message.summary ? <span>{message.summary}</span> : null}
                    <div className="chat__actions" aria-label="Message actions">
                      <button type="button" onClick={() => onMessageAction?.(conversation.id, message.id, "pin")}>
                        Pin
                      </button>
                      <button type="button" onClick={() => onMessageAction?.(conversation.id, message.id, "copy")}>
                        Copy
                      </button>
                      <button type="button" onClick={() => onMessageAction?.(conversation.id, message.id, "follow-up")}>
                        Follow up
                      </button>
                    </div>
                  </footer>
                </article>
              ))}
            </section>
          ))}
        </div>

        <form className="chat__composer" onSubmit={handleComposerSubmit}>
          <div className="chat__composer-inner">
            <div className="chat__attachments" aria-label="Attachment controls">
              <button type="button" onClick={handleAttachmentClick} title="Upload file">
                <ComposerIcon name="paperclip" />
              </button>
              <button type="button" title="Capture photo">
                <ComposerIcon name="camera" />
              </button>
            </div>
            <textarea
              value={composerValue}
              onChange={handleComposerChange}
              placeholder="Share updates, requests, or questions for the site team"
              aria-label="Message composer"
            />
            <div className="chat__controls">
              <input
                ref={fileInputRef}
                type="file"
                className="chat__hidden-input"
                onChange={handleFileChange}
              />
              <button
                type="button"
                className={`chat__mic ${microphoneEnabled ? "" : "chat__mic--disabled"}`}
                onClick={handleMicToggle}
                aria-pressed={microphoneEnabled}
                title={microphoneEnabled ? "Mute microphone" : "Enable microphone"}
              >
                <ComposerIcon name="microphone" isActive={microphoneEnabled} />
              </button>
              <button type="submit" className="chat__send" disabled={!composerValue.trim()}>
                Send
              </button>
            </div>
          </div>
          {!microphoneEnabled ? (
            <p className="chat__mic-warning">Enable your microphone to capture a quick voice note.</p>
          ) : null}
        </form>
      </div>

      <aside className="context-panel" aria-label="Conversation context">
        <div className="context-panel__tabs" role="tablist" aria-label="Contextual insights">
          {contextTabs.map((tab) => {
            const selected = tab.id === activeContextTab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setActiveTab(tab.id)}
              >
                <ContextIcon type={tab.id} isActive={selected} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <div className="context-panel__content" role="tabpanel">
          <h3>{activeContextTab.label}</h3>
          <ul>
            {activeContextTab.items.map((item, index) => (
              <li key={`${activeContextTab.id}-${index}`}>
                <p>{item}</p>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </>
  );
}
