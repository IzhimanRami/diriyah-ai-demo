# backend/api/routes/workspace.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

@router.get("/shell")
def get_workspace_shell():
    """
    Minimal 'workspace shell' payload so the frontend can boot.
    Adjust to match what your UI expects if needed.
    """
    return {
        "id": "demo",
        "name": "Demo Workspace",
        "projects": [
            {"id": "fixtures", "name": "Fixture BOQ", "status": "ready"}
        ]
    }
