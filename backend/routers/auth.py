"""
MailScrub.app — Auth Router
Version: 1.0.0 (Official Release)

Routes d'authentification OAuth 2.0 avec Google.
Flux : /auth/login → Google → /auth/callback → session
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from google_auth_oauthlib.flow import Flow

router = APIRouter(prefix="/auth", tags=["auth"])

# ── OAuth Config ──────────────────────────────────────────────
import json
import base64

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.modify"
]

# Allow HTTP only for local development
if os.getenv("K_SERVICE"):
    # Running on Cloud Run → force HTTPS
    os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
else:
    # Local dev → allow HTTP
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def _get_redirect_uri(request: Request) -> str:
    """
    Build the OAuth callback URI, forcing HTTPS on Cloud Run.
    Cloud Run sits behind a reverse proxy that terminates TLS,
    so request.url_for() may return http:// even though the
    actual public URL is https://.
    """
    url = str(request.url_for("callback"))

    # On Cloud Run, force https
    if os.getenv("K_SERVICE"):
        url = url.replace("http://", "https://")
    else:
        # Local dev: Force localhost to match Google Console allowlist
        # even if accessed via 127.0.0.1
        url = url.replace("127.0.0.1", "localhost")

    return url


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
    redirect_uri = _get_redirect_uri(request)

    flow = _get_flow(redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
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
    redirect_uri = _get_redirect_uri(request)

    flow = _get_flow(redirect_uri)

    # Relax scope enforcement: prevents crash if Google returns different scopes
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    try:
        # Exchange the authorization code for credentials
        flow.fetch_token(code=code)
    except Exception as e:
        print(f"[ERROR] OAuth fetch_token failed: {e}")
        return RedirectResponse("/?error=oauth_failed")

    credentials = flow.credentials

    # Verify we got the required scope
    if "https://www.googleapis.com/auth/gmail.modify" not in credentials.scopes:
        return RedirectResponse("/?error=missing_scope")

    # Store credentials in session (serialized)
    request.session["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes),
    }

    # Decode id_token to get user profile
    if credentials.id_token:
        try:
            # JWT format: header.payload.signature
            payload_segment = credentials.id_token.split('.')[1]
            # Add padding
            padding = '=' * (4 - len(payload_segment) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_segment + padding)
            payload = json.loads(payload_bytes)
            
            request.session["user_profile"] = {
                "email": payload.get("email"),
                "picture": payload.get("picture"),
                "name": payload.get("name")
            }
        except Exception as e:
            print(f"[WARNING] Could not decode id_token: {e}")

    # Redirect to the dashboard (frontend will detect auth and start analysis)
    return RedirectResponse("/?authenticated=true")


@router.get("/status")
async def auth_status(request: Request):
    """Vérifie si l'utilisateur est connecté (a des credentials en session) et renvoie son profil."""
    creds = request.session.get("credentials")
    profile = request.session.get("user_profile")
    
    if creds:
        return {
            "authenticated": True,
            "mode": "gmail",
            "profile": profile
        }
    return {
        "authenticated": False,
        "mode": "none",
        "profile": None
    }


@router.get("/logout")
async def logout(request: Request):
    """Déconnecte l'utilisateur en supprimant la session."""
    request.session.clear()
    return RedirectResponse("/")
