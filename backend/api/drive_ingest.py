# backend/api/drive_ingest.py

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from backend.services.drive_service import (
    list_files_in_folder_via_api_key,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_file_obj(file_obj: Any) -> Dict[str, Any]:
    """
    Make sure whatever list_files_in_folder_via_api_key returns
    can be safely serialized to JSON.
    """
    if isinstance(file_obj, dict):
        return file_obj
    # fallback for dataclass / simple objects
    return {
        k: getattr(file_obj, k)
        for k in dir(file_obj)
        if not k.startswith("_") and not callable(getattr(file_obj, k))
    }


@router.api_route("/drive/ingest", methods=["POST", "GET"])
async def ingest_drive_folder(
    folder_id: str = Query(..., alias="folderId"),
):
    """
    Ingest a public Google Drive folder using the API key–based helper.

    For now this:
      * lists all files in the folder using list_files_in_folder_via_api_key
      * returns them as JSON
    This keeps the endpoint stable (no 502) and lets us verify Drive access.
    Once this is confirmed working, we can plug in the Chroma/vector
    indexing logic on top of this list of files.
    """
    try:
        logger.info("Starting ingest for folder %s", folder_id)

        files: List[Any] = list_files_in_folder_via_api_key(folder_id)
        files_serialized = [_serialize_file_obj(f) for f in files]

        logger.info(
            "Ingest completed for folder %s, %d files found",
            folder_id,
            len(files_serialized),
        )

        return {
            "folderId": folder_id,
            "fileCount": len(files_serialized),
            "files": files_serialized,
        }

    except Exception as exc:  # noqa: BLE001 – we want to log any crash here
        logger.exception("Drive ingest failed for folder %s", folder_id)
        # This returns a normal 500 JSON response instead of crashing the worker
        raise HTTPException(
            status_code=500,
            detail=f"Drive ingest failed: {exc}",
        ) from exc
