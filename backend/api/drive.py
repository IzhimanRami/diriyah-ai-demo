from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import RedirectResponse, JSONResponse

from backend.services.google_drive import upload_to_drive, oauth_flow

router = APIRouter()

# ------------------ Existing upload endpoint (service account) ----------------

@router.post("/drive/upload")
async def drive_upload(file: UploadFile = File(...)):
    """
    Upload a file to Google Drive using the service-account integration.
    Falls back to a stubbed ID if the backend is running in stub mode.
    """
    file_id = upload_to_drive(file)
    return {"file_id": file_id}


# ------------------ NEW: OAuth endpoints (user consent) ----------------------

@router.get("/drive/oauth2start")
def drive_oauth2start():
    """
    Kick off Google OAuth by redirecting the user to the consent screen.
    Uses GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI and GOOGLE_SCOPES from env.
    """
    flow = oauth_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    # You may want to set a secure cookie with `state` if you intend to verify it.
    return RedirectResponse(auth_url)


@router.get("/drive/oauth2callback")
def drive_oauth2callback(request: Request):
    """
    Handle Google OAuth redirect, exchange the auth code for tokens.
    For production, store the credentials securely (DB/KMS). Here we return them
    so you can verify the flow works end-to-end.
    """
    flow = oauth_flow()
    flow.fetch_token(authorization_response=str(request.url))
    creds = flow.credentials

    # NOTE: Do NOT return tokens in production. Persist them securely and return a success page.
    return JSONResponse(
        {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "scopes": creds.scopes,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
        }
    )
