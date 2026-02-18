"""
MailScrub.app — Auth Router

Routes d'authentification OAuth 2.0 avec Google.
Flux : /auth/login → Google → /auth/callback → session
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from google_auth_oauthlib.flow import Flow

router = APIRouter(prefix="/auth", tags=["auth"])

# ── OAuth Config ──────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Allow HTTP for local dev (OAuth lib requires HTTPS by default)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def _get_flow(redirect_uri: str) -> Flow:
    """Create a Google OAuth flow from env vars."""
    client_config = {
        "web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = redirect_uri
    return flow


# ── Routes ────────────────────────────────────────────────────


@router.get("/login")
async def login(request: Request):
    """
    Redirige l'utilisateur vers l'écran de consentement Google.
    """
    # Build the callback URL dynamically based on the current request
    redirect_uri = str(request.url_for("callback"))

    flow = _get_flow(redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    # Store state in session for CSRF protection
    request.session["oauth_state"] = state

    return RedirectResponse(authorization_url)


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    """
    Callback OAuth — reçoit le code de Google, échange contre un token,
    et stocke les credentials dans la session.
    """
    redirect_uri = str(request.url_for("callback"))

    flow = _get_flow(redirect_uri)

    # Exchange the authorization code for credentials
    flow.fetch_token(code=code)

    credentials = flow.credentials

    # Store credentials in session (serialized)
    request.session["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes),
    }

    # Redirect to the dashboard (frontend will detect auth and start analysis)
    return RedirectResponse("/?authenticated=true")


@router.get("/status")
async def auth_status(request: Request):
    """Vérifie si l'utilisateur est connecté (a des credentials en session)."""
    creds = request.session.get("credentials")
    if creds:
        return {
            "authenticated": True,
            "mode": "gmail",
        }
    return {
        "authenticated": False,
        "mode": "none",
    }


@router.get("/logout")
async def logout(request: Request):
    """Déconnecte l'utilisateur en supprimant la session."""
    request.session.clear()
    return RedirectResponse("/")
