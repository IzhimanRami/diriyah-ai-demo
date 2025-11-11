"""Workspace APIs backing the interactive sidebar and chat surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Dict, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict


# NOTE: main.py mounts this router with prefix="/api",
# so all routes below end up as:
#   /api/workspace/shell
#   /api/workspace/active-project
#   /api/workspace/chats ...
router = APIRouter()


class ProjectModel(BaseModel):
    """Project details exposed to the frontend shell."""
    id: str
    name: str
    location: str
    phase: str


class ChatSummaryModel(BaseModel):
    """Metadata describing a conversation in the sidebar."""
    id: str
    title: str
    preview: str
    timestamp: str
    unread: int = 0
    is_draft: bool = Field(default=False, alias="isDraft")

    model_config = ConfigDict(populate_by_name=True)


class ChatGroupModel(BaseModel):
    """Sidebar grouping of conversations."""
    id: str
    label: str
    chats: List[ChatSummaryModel]
    default_collapsed: bool | None = Field(default=None, alias="defaultCollapsed")

    model_config = ConfigDict(populate_by_name=True)


class MessageModel(BaseModel):
    """Representation of a single chat message."""
    id: str
    role: str
    author: str
    timestamp: str
    body: str
    summary: str | None = None


class TimelineEntryModel(BaseModel):
    """A chronological block of messages."""
    id: str
    label: str
    messages: List[MessageModel]


class ConversationContextModel(BaseModel):
    """Supplementary context surfaced in the insights panel."""
    summary: List[str]
    tasks: List[str]
    files: List[str]
    activity: List[str]


class ConversationModel(BaseModel):
    """Detailed conversation payload consumed by the chat workspace."""
    id: str
    title: str
    last_activity: str = Field(alias="lastActivity")
    is_live: bool = Field(alias="isLive")
    timeline: List[TimelineEntryModel]
    context: ConversationContextModel

    model_config = ConfigDict(populate_by_name=True)


class WorkspaceShellModel(BaseModel):
    """Aggregate data required to render the application shell."""
    projects: List[ProjectModel]
    chat_groups: List[ChatGroupModel] = Field(alias="chatGroups")
    conversations: Dict[str, ConversationModel]
    active_project_id: str = Field(alias="activeProjectId")
    active_chat_id: str = Field(alias="activeChatId")
    microphone_enabled: bool = Field(alias="microphoneEnabled")

    model_config = ConfigDict(populate_by_name=True)


class ConversationUpdateModel(BaseModel):
    """State update emitted after mutating chat data."""
    conversation: ConversationModel
    chat_groups: List[ChatGroupModel] = Field(alias="chatGroups")

    model_config = ConfigDict(populate_by_name=True)


class MessageCreateRequest(BaseModel):
    """Payload captured when a user submits a new message."""
    body: str
    project_id: str | None = Field(default=None, alias="projectId")


class AttachmentCreateRequest(BaseModel):
    """Attachment metadata registered with a conversation."""
    file_name: str = Field(alias="fileName")


class MicrophoneStateRequest(BaseModel):
    """Toggle the microphone capture state."""
    enabled: bool


class CreateChatRequest(BaseModel):
    """Provision a new draft conversation for a project."""
    project_id: str = Field(alias="projectId")


class ActiveProjectRequest(BaseModel):
    """Update the active project used to scope workspace calls."""
    project_id: str = Field(alias="projectId")


class MessageActionRequest(BaseModel):
    """Capture a user action taken on a message."""
    action: str


@dataclass
class WorkspaceState:
    """In-memory workspace backing store for demo interactions."""
    projects: List[ProjectModel]
    chat_groups: List[ChatGroupModel]
    conversations: Dict[str, ConversationModel]
    active_project_id: str
    active_chat_id: str
    microphone_enabled: bool = False
    _lock: RLock = field(default_factory=RLock, repr=False)

    def snapshot(self) -> WorkspaceShellModel:
        with self._lock:
            return WorkspaceShellModel(
                projects=self.projects,
                chat_groups=self.chat_groups,
                conversations=self.conversations,
                active_project_id=self.active_project_id,
                active_chat_id=self.active_chat_id,
                microphone_enabled=self.microphone_enabled,
            )

    def _touch_chat_preview(self, chat_id: str, preview: str, timestamp: str) -> None:
        for group in self.chat_groups:
            for chat in group.chats:
                if chat.id == chat_id:
                    chat.preview = preview
                    chat.timestamp = timestamp
                    return

    def _mark_chat_read(self, chat_id: str) -> None:
        for group in self.chat_groups:
            for chat in group.chats:
                if chat.id == chat_id:
                    chat.unread = 0
                    return

    def _increment_unread(self, chat_id: str) -> None:
        for group in self.chat_groups:
            for chat in group.chats:
                if chat.id == chat_id:
                    chat.unread += 1
                    return

    def _add_chat_to_group(self, chat: ChatSummaryModel, group_id: str = "pinned") -> None:
        for group in self.chat_groups:
            if group.id == group_id:
                group.chats.insert(0, chat)
                return
        raise HTTPException(status_code=500, detail=f"Chat group '{group_id}' not found")

    def get_conversation(self, chat_id: str) -> ConversationModel:
        with self._lock:
            try:
                return self.conversations[chat_id]
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"Conversation '{chat_id}' not found") from exc

    def register_attachment(self, chat_id: str, file_name: str) -> ConversationModel:
        with self._lock:
            conversation = self.get_conversation(chat_id)
            if file_name not in conversation.context.files:
                conversation.context.files.append(file_name)
                conversation.context.activity.insert(0, f"{self._now_display()} Attachment added: {file_name}")
            return conversation

    def create_message(self, chat_id: str, body: str, author: str = "You") -> ConversationModel:
        message = MessageModel(
            id=f"msg-{uuid4().hex[:8]}",
            role="user",
            author=author,
            timestamp=self._now_display(),
            body=body,
        )
        with self._lock:
            conversation = self.get_conversation(chat_id)
            conversation.last_activity = f"{message.timestamp} • Posted update"
            if conversation.timeline:
                conversation.timeline[0].messages.append(message)
            else:
                conversation.timeline.append(
                    TimelineEntryModel(id="live", label="Live", messages=[message])
                )
            self._touch_chat_preview(chat_id, body[:72], "Now")
            conversation.context.activity.insert(0, f"{message.timestamp} Update captured: {body[:60]}")
            return conversation

    def log_assistant_action(self, chat_id: str, summary: str) -> None:
        with self._lock:
            conversation = self.get_conversation(chat_id)
            conversation.context.activity.insert(0, summary)
            self._increment_unread(chat_id)

    def create_chat(self, project_id: str) -> ConversationModel:
        with self._lock:
            project = next((p for p in self.projects if p.id == project_id), None)
            if project is None:
                raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

            chat_id = f"draft-{uuid4().hex[:6]}"
            title = f"{project.name} quick briefing"
            timestamp = self._now_display()

            conversation = ConversationModel(
                id=chat_id,
                title=title,
                last_activity=f"Draft • {project.name}",
                is_live=False,
                timeline=[
                    TimelineEntryModel(
                        id="draft",
                        label="Draft",
                        messages=[
                            MessageModel(
                                id=f"msg-{uuid4().hex[:8]}",
                                role="assistant",
                                author="Diriyah Brain",
                                timestamp=timestamp,
                                body="Let's capture objectives for this channel and assign first actions.",
                                summary="Draft channel ready",
                            )
                        ],
                    )
                ],
                context=ConversationContextModel(
                    summary=["Outline agenda for stakeholder sync."],
                    tasks=["Capture first three priorities."],
                    files=[],
                    activity=[f"{timestamp} Draft channel created."],
                ),
            )

            chat = ChatSummaryModel(
                id=chat_id,
                title=title,
                preview="Draft briefing ready to capture notes",
                timestamp="Draft",
                unread=0,
                is_draft=True,
            )

            self.conversations[chat_id] = conversation
            self._add_chat_to_group(chat)
            self.active_chat_id = chat_id
            return conversation

    def set_microphone(self, enabled: bool) -> bool:
        with self._lock:
            self.microphone_enabled = enabled
            return self.microphone_enabled

    def set_active_project(self, project_id: str) -> None:
        with self._lock:
            if not any(project.id == project_id for project in self.projects):
                raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
            self.active_project_id = project_id

    def set_active_chat(self, chat_id: str) -> ConversationModel:
        with self._lock:
            conversation = self.get_conversation(chat_id)
            self.active_chat_id = chat_id
            self._mark_chat_read(chat_id)
            return conversation

    def _now_display(self) -> str:
        return datetime.utcnow().strftime("%H:%M")


def _seed_state() -> WorkspaceState:
    """Initialise the interactive workspace with representative data."""

    projects = [
        ProjectModel(id="villa-100", name="Villa 100", location="Diriyah South", phase="Structure"),
        ProjectModel(id="tower-20", name="Tower 20", location="Cultural Spine", phase="Facade"),
        ProjectModel(id="gateway-villas", name="Gateway Villas", location="Northern Gateway", phase="MEP Rough-in"),
        ProjectModel(id="cultural-district", name="Cultural District", location="Heritage Quarter", phase="Fit-out"),
    ]

    chat_groups = [
        ChatGroupModel(
            id="pinned",
            label="Pinned",
            chats=[
                ChatSummaryModel(
                    id="villa-ops",
                    title="Villa 100 daily sync",
                    preview="Pour approved • Workforce ramp up confirmed",
                    timestamp="09:24",
                    unread=2,
                ),
                ChatSummaryModel(
                    id="tower-logistics",
                    title="Tower 20 logistics",
                    preview="Confirm revised crane schedule for slab C",
                    timestamp="Yesterday",
                ),
                ChatSummaryModel(
                    id="new-briefing",
                    title="New project briefing",
                    preview="Draft agenda ready to capture actions",
                    timestamp="Draft",
                    is_draft=True,
                ),
            ],
        ),
        ChatGroupModel(
            id="recent",
            label="Recent",
            chats=[
                ChatSummaryModel(
                    id="facade-review",
                    title="Facade mock-up review",
                    preview="Invite issued to design authority",
                    timestamp="Mon",
                    unread=1,
                ),
                ChatSummaryModel(
                    id="cultural-programme",
                    title="Cultural District programme",
                    preview="Sequence re-baselined with night shift",
                    timestamp="Sun",
                ),
            ],
        ),
        ChatGroupModel(
            id="archive",
            label="Archive",
            default_collapsed=True,
            chats=[
                ChatSummaryModel(
                    id="handover-packages",
                    title="Handover packages",
                    preview="Snag list closed out for villas 12-18",
                    timestamp="May 08",
                )
            ],
        ),
    ]

    conversations: Dict[str, ConversationModel] = {
        "villa-ops": ConversationModel(
            id="villa-ops",
            title="Villa 100 daily sync",
            last_activity="Live now • Site command room",
            is_live=True,
            timeline=[
                TimelineEntryModel(
                    id="today",
                    label="Today",
                    messages=[
                        MessageModel(
                            id="msg-1",
                            role="assistant",
                            author="Diriyah Brain",
                            timestamp="09:24",
                            body="Morning team! Structural pour for podium slab section B cleared with procurement overnight.",
                            summary="Pour clearance confirmed",
                        ),
                        MessageModel(
                            id="msg-2",
                            role="user",
                            author="Khalid",
                            timestamp="09:26",
                            body="Capture the actions for labour ramp up and notify HR about overtime requirements.",
                            summary="Log labour actions",
                        ),
                        MessageModel(
                            id="msg-3",
                            role="assistant",
                            author="Diriyah Brain",
                            timestamp="09:27",
                            body=(
                                "Added two follow-up actions: workforce ramp up sign-off and HR overtime approval. "
                                "Assigned to Fatimah with 18:00 deadline."
                            ),
                            summary="Created follow-up actions",
                        ),
                    ],
                ),
                TimelineEntryModel(
                    id="yesterday",
                    label="Yesterday",
                    messages=[
                        MessageModel(
                            id="msg-4",
                            role="assistant",
                            author="Diriyah Brain",
                            timestamp="18:42",
                            body=(
                                "Generated daily summary: procurement signed concrete mix revision, logistics approved "
                                "overnight deliveries for Cultural District."
                            ),
                            summary="Daily summary issued",
                        )
                    ],
                ),
            ],
            context=ConversationContextModel(
                summary=[
                    "Villa 100 pour approved with revised mix design.",
                    "Labour ramp up pending HR overtime confirmation.",
                    "Stakeholder briefing scheduled for 16:30.",
                ],
                tasks=[
                    "Issue overtime approval memo for site crew.",
                    "Upload inspection photos for podium slab section B.",
                    "Share updated BOQ alignment with finance.",
                ],
                files=[
                    "Pour sequence - Rev 12.pdf",
                    "Daily briefing deck.pptx",
                    "Overtime request template.docx",
                ],
                activity=[
                    "09:18 Fatimah completed logistics cross-check.",
                    "08:52 Diriyah Brain synced overnight procurement updates.",
                    "07:45 Khalid pinned tomorrow's priorities.",
                ],
            ),
        ),
        "tower-logistics": ConversationModel(
            id="tower-logistics",
            title="Tower 20 logistics",
            last_activity="Yesterday • Logistics control",
            is_live=False,
            timeline=[
                TimelineEntryModel(
                    id="yesterday",
                    label="Yesterday",
                    messages=[
                        MessageModel(
                            id="msg-5",
                            role="assistant",
                            author="Diriyah Brain",
                            timestamp="17:08",
                            body="Confirmed delivery slot swap for crane 3. Updated route to avoid Cultural Spine closure.",
                            summary="Route updated",
                        ),
                        MessageModel(
                            id="msg-6",
                            role="user",
                            author="Maha",
                            timestamp="17:12",
                            body="Share revised lifting plan with safety by 10:00 tomorrow.",
                            summary="Share lifting plan",
                        ),
                    ],
                )
            ],
            context=ConversationContextModel(
                summary=[
                    "Crane 3 delivery rescheduled to 04:30.",
                    "Temporary access clearance secured with security.",
                    "Awaiting safety sign-off on revised lifting plan.",
                ],
                tasks=[
                    "Send lifting plan to safety (due 10:00).",
                    "Notify subcontractor about night shift logistics.",
                ],
                files=[
                    "Tower20_lifting-plan_rev4.pdf",
                    "Night-shift-logistics.xlsx",
                ],
                activity=[
                    "17:12 Maha requested safety circulation.",
                    "16:55 Diriyah Brain logged revised delivery slot.",
                ],
            ),
        ),
        "new-briefing": ConversationModel(
            id="new-briefing",
            title="New project briefing",
            last_activity="Draft agenda",
            is_live=False,
            timeline=[
                TimelineEntryModel(
                    id="draft",
                    label="Draft",
                    messages=[
                        MessageModel(
                            id="msg-7",
                            role="assistant",
                            author="Diriyah Brain",
                            timestamp="08:14",
                            body="I'll keep this space ready to capture agenda items once you add the briefing outline.",
                            summary="Awaiting agenda",
                        )
                    ],
                )
            ],
            context=ConversationContextModel(
                summary=[
                    "Create agenda for new stakeholder briefing.",
                    "Confirm attendees from operations and finance.",
                ],
                tasks=[
                    "Draft briefing outline for leadership review.",
                    "Collect latest progress stats from Villa 100.",
                ],
                files=["Stakeholder_briefing_template.pptx"],
                activity=["Draft channel created by Khalid."],
            ),
        ),
        "facade-review": ConversationModel(
            id="facade-review",
            title="Facade mock-up review",
            last_activity="Mon • Design coordination",
            is_live=False,
            timeline=[
                TimelineEntryModel(
                    id="mon",
                    label="Mon",
                    messages=[
                        MessageModel(
                            id="msg-8",
                            role="assistant",
                            author="Diriyah Brain",
                            timestamp="13:05",
                            body="Reminder: mock-up review with design authority on Thursday. Materials inspection pack attached.",
                            summary="Review reminder",
                        )
                    ],
                )
            ],
            context=ConversationContextModel(
                summary=[
                    "Mock-up review booked for Thursday 09:00.",
                    "Lighting sample pending electrical approval.",
                ],
                tasks=["Send logistics plan to design team."],
                files=["Mockup_materials_pack.zip"],
                activity=["13:05 Reminder issued to design authority."],
            ),
        ),
        "cultural-programme": ConversationModel(
            id="cultural-programme",
            title="Cultural District programme",
            last_activity="Sun • Programme office",
            is_live=False,
            timeline=[
                TimelineEntryModel(
                    id="sun",
                    label="Sun",
                    messages=[
                        MessageModel(
                            id="msg-9",
                            role="assistant",
                            author="Diriyah Brain",
                            timestamp="11:20",
                            body="Night shift sequence integrated into master schedule. Highlighted risks for utilities corridor.",
                            summary="Schedule updated",
                        )
                    ],
                )
            ],
            context=ConversationContextModel(
                summary=[
                    "Night shift enabled to regain 2 days on programme.",
                    "Utilities corridor needs clash detection review.",
                ],
                tasks=["Coordinate clash review with BIM team."],
                files=["Programme_rev21.mpp"],
                activity=["11:20 Schedule sync complete."],
            ),
        ),
        "handover-packages": ConversationModel(
            id="handover-packages",
            title="Handover packages",
            last_activity="May 08 • QA/QC",
            is_live=False,
            timeline=[
                TimelineEntryModel(
                    id="may08",
                    label="May 08",
                    messages=[
                        MessageModel(
                            id="msg-10",
                            role="assistant",
                            author="Diriyah Brain",
                            timestamp="16:18",
                            body="Snag list for villas 12-18 closed. Issued handover packs to client representative.",
                            summary="Snag list closed",
                        )
                    ],
                )
            ],
            context=ConversationContextModel(
                summary=["All handover documentation submitted to client."],
                tasks=["Schedule client walk-through for villas 19-24."],
                files=["Villa12-18_handover.zip"],
                activity=["16:18 Handover pack shared with client rep."],
            ),
        ),
    }

    return WorkspaceState(
        projects=projects,
        chat_groups=chat_groups,
        conversations=conversations,
        active_project_id=projects[0].id,
        active_chat_id="villa-ops",
        microphone_enabled=False,
    )


_STATE = _seed_state()


@router.get("/workspace/shell", response_model=WorkspaceShellModel)
def get_workspace_shell() -> WorkspaceShellModel:
    """Return the aggregated application shell state."""
    return _STATE.snapshot()


@router.post("/workspace/active-project", response_model=WorkspaceShellModel)
def set_active_project(request: ActiveProjectRequest) -> WorkspaceShellModel:
    """Persist the active project selection and emit the new shell state."""
    _STATE.set_active_project(request.project_id)
    return _STATE.snapshot()


@router.post("/workspace/chats", response_model=ConversationUpdateModel)
def create_chat(request: CreateChatRequest) -> ConversationUpdateModel:
    """Create a new draft conversation scoped to the selected project."""
    conversation = _STATE.create_chat(request.project_id)
    return ConversationUpdateModel(conversation=conversation, chat_groups=_STATE.chat_groups)


@router.post("/workspace/chats/{chat_id}/read", response_model=ConversationUpdateModel)
def mark_chat_read(chat_id: str) -> ConversationUpdateModel:
    """Set a conversation as the active thread and reset its unread badge."""
    conversation = _STATE.set_active_chat(chat_id)
    return ConversationUpdateModel(conversation=conversation, chat_groups=_STATE.chat_groups)


@router.post("/workspace/chats/{chat_id}/messages", response_model=ConversationUpdateModel)
def submit_message(chat_id: str, request: MessageCreateRequest) -> ConversationUpdateModel:
    """Capture a user-authored message in the conversation timeline."""
    if not request.body.strip():
        raise HTTPException(status_code=400, detail="Message body cannot be empty")
    conversation = _STATE.create_message(chat_id, request.body)
    return ConversationUpdateModel(conversation=conversation, chat_groups=_STATE.chat_groups)


@router.post("/workspace/chats/{chat_id}/attachments", response_model=ConversationModel)
def register_attachment(chat_id: str, request: AttachmentCreateRequest) -> ConversationModel:
    """Associate an uploaded file with a conversation."""
    if not request.file_name.strip():
        raise HTTPException(status_code=400, detail="File name cannot be empty")
    return _STATE.register_attachment(chat_id, request.file_name)


@router.post("/workspace/microphone", response_model=MicrophoneStateRequest)
def toggle_microphone(request: MicrophoneStateRequest) -> MicrophoneStateRequest:
    """Update the microphone capture state."""
    enabled = _STATE.set_microphone(request.enabled)
    return MicrophoneStateRequest(enabled=enabled)


@router.put("/workspace/messages/{message_id}/action")
def record_message_action(message_id: str, request: MessageActionRequest) -> dict[str, str]:
    """Record a lightweight audit trail for message-level quick actions."""
    if not request.action.strip():
        raise HTTPException(status_code=400, detail="Action must be provided")
    summary = f"{datetime.utcnow().strftime('%H:%M')} Action '{request.action}' recorded for message {message_id}."
    _STATE.log_assistant_action(_STATE.active_chat_id, summary)
    return {"status": "recorded"}


def _reset_state_for_tests() -> None:
    """Re-initialise the workspace state for isolated testing."""
    global _STATE
    _STATE = _seed_state()
