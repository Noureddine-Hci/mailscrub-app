"""
MailScrub.app — Auth Router
Version: 1.1.0 (Multi-provider)

Routes d'authentification :
    - Google    : /auth/login → Google → /auth/callback → session
    - Microsoft : /auth/microsoft/login → Microsoft → /auth/microsoft/callback → session
    - IMAP/POP  : POST /auth/imap/connect (pas de redirect OAuth — identifiants directs)
"""

import base64
import hashlib
import imaplib
import json
import os
import poplib
import secrets
import socket
import ssl
import time

import requests
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from google_auth_oauthlib.flow import Flow

from backend.src.providers.microsoft_provider import MICROSOFT_SCOPES, get_msal_app
from backend.src.providers.imap_provider import ImapProviderClient
from backend.src.providers.pop_provider import PopProviderClient
from backend.src.providers.mail_host_presets import all_presets, get_preset
from backend.src.security.crypto import encrypt_secret

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.modify"
]

GRAPH_TIMEOUT = 10

# Allow HTTP only for local development
if os.getenv("ENV") == "production":
    # Production → force HTTPS
    os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
else:
    # Local dev → allow HTTP
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def _get_redirect_uri(request: Request, route_name: str = "callback") -> str:
    """
    Build the OAuth callback URI, forcing HTTPS in production.
    Azure ACA (like Cloud Run) sits behind a reverse proxy that terminates TLS,
    so request.url_for() may return http:// even though the public URL is https://.

    `route_name` doit être le nom de fonction EXACT de la route callback visée
    (request.url_for résout par nom, et renvoie la première route enregistrée
    sous ce nom — d'où l'obligation d'un nom distinct par provider : "callback"
    pour Google, "microsoft_callback" pour Microsoft).
    """
    url = str(request.url_for(route_name))

    # In production, force https (proxy terminates TLS)
    if os.getenv("ENV") == "production":
        url = url.replace("http://", "https://")
    else:
        # Local dev: Force localhost to match Google/Microsoft console allowlist
        # even if accessed via 127.0.0.1
        url = url.replace("127.0.0.1", "localhost")

    return url


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge_S256) for PKCE."""
    verifier = secrets.token_urlsafe(96)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


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
    # Disable auto-PKCE from requests-oauthlib 2.x so we control it ourselves
    if hasattr(flow.oauth2session, "code_challenge_method"):
        flow.oauth2session.code_challenge_method = None
    return flow


# ── Routes ────────────────────────────────────────────────────


@router.get("/login")
async def login(request: Request):
    """
    Redirige l'utilisateur vers l'écran de consentement Google.
    """
    redirect_uri = _get_redirect_uri(request)

    flow = _get_flow(redirect_uri)
    code_verifier, code_challenge = _pkce_pair()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )

    request.session["oauth_state"] = state
    request.session["oauth_code_verifier"] = code_verifier

    return RedirectResponse(authorization_url)


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    """
    Callback OAuth — reçoit le code de Google, échange contre un token,
    et stocke les credentials dans la session.
    """
    # Protection CSRF : le state renvoyé par Google doit correspondre à celui
    # généré dans /auth/login et stocké en session. Sans cette vérification,
    # un attaquant peut injecter son propre code d'autorisation.
    expected_state = request.session.pop("oauth_state", None)
    if not state or not expected_state or state != expected_state:
        print("[WARN] OAuth state invalide ou manquant (CSRF potentiel).")
        return RedirectResponse("/?error=invalid_state")

    redirect_uri = _get_redirect_uri(request)

    flow = _get_flow(redirect_uri)

    # Relax scope enforcement: prevents crash if Google returns different scopes
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    code_verifier = request.session.pop("oauth_code_verifier", None)

    try:
        flow.fetch_token(code=code, code_verifier=code_verifier)
    except Exception as e:
        print(f"[ERROR] OAuth fetch_token failed: {e}")
        return RedirectResponse("/?error=oauth_failed")

    credentials = flow.credentials

    # Verify we got the required scope
    if "https://www.googleapis.com/auth/gmail.modify" not in credentials.scopes:
        return RedirectResponse("/?error=missing_scope")

    # Store credentials in session (serialized).
    # SÉCURITÉ : le cookie de session est signé mais PAS chiffré (base64 lisible
    # côté client). On n'y stocke donc jamais le client_secret de l'application ;
    # il est ré-injecté depuis l'environnement serveur au moment de construire
    # le service Gmail (voir routers/analysis.py).
    request.session["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "scopes": list(credentials.scopes),
    }
    request.session["provider"] = "google"

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
    """Vérifie si l'utilisateur est connecté et renvoie son provider + profil."""
    creds = request.session.get("credentials")
    profile = request.session.get("user_profile")

    # Compat : une session créée avant l'introduction du champ "provider" a des
    # credentials Google mais pas cette clé. Sans ce repli, ces utilisateurs déjà
    # connectés seraient traités comme déconnectés dès ce déploiement.
    provider = request.session.get("provider") or ("google" if creds else None)

    if creds and provider:
        return {
            "authenticated": True,
            "provider": provider,
            "profile": profile,
        }
    return {
        "authenticated": False,
        "provider": None,
        "profile": None,
    }


@router.get("/logout")
async def logout(request: Request):
    """Déconnecte l'utilisateur en supprimant la session."""
    request.session.clear()
    return RedirectResponse("/")


# ── Microsoft / Outlook ──────────────────────────────────────
#
# Noms de fonctions volontairement distincts de login()/callback() : l'app
# résout les redirect_uri OAuth via request.url_for(<nom de fonction>), qui
# retourne la PREMIÈRE route enregistrée sous ce nom. Un callback Microsoft
# nommé "callback" comme celui de Google résoudrait silencieusement vers
# /auth/callback (Google) au lieu du sien.


@router.get("/microsoft/login")
async def microsoft_login(request: Request):
    """Redirige l'utilisateur vers l'écran de consentement Microsoft."""
    redirect_uri = _get_redirect_uri(request, "microsoft_callback")
    msal_app = get_msal_app()

    # initiate_auth_code_flow gère state + PKCE nativement (contrairement à
    # Google où requests-oauthlib 2.x nous a forcés à un contournement manuel
    # — voir _pkce_pair()). Le flow entier (state, code_verifier, ...) est
    # stocké en session, aucun secret applicatif dedans (le client_secret
    # n'est ré-injecté que côté serveur, dans _get_msal_app()).
    flow = msal_app.initiate_auth_code_flow(
        scopes=MICROSOFT_SCOPES,
        redirect_uri=redirect_uri,
    )
    request.session["ms_oauth_flow"] = flow

    return RedirectResponse(flow["auth_uri"])


@router.get("/microsoft/callback")
async def microsoft_callback(request: Request):
    """
    Callback OAuth Microsoft — reçoit le code, échange contre un token via MSAL,
    et stocke les credentials dans la session.
    """
    flow = request.session.pop("ms_oauth_flow", None)
    if not flow:
        print("[WARN] Microsoft OAuth : flow manquant en session (CSRF potentiel ou session expirée).")
        return RedirectResponse("/?error=invalid_state")

    msal_app = get_msal_app()

    try:
        # acquire_token_by_auth_code_flow valide le state en interne (lève
        # ValueError en cas de mismatch — protection CSRF déjà assurée par MSAL).
        result = msal_app.acquire_token_by_auth_code_flow(flow, dict(request.query_params))
    except ValueError as e:
        print(f"[WARN] Microsoft OAuth state invalide : {e}")
        return RedirectResponse("/?error=invalid_state")

    if "error" in result:
        print(f"[ERROR] Microsoft OAuth échoué : {result.get('error_description', result.get('error'))}")
        return RedirectResponse("/?error=oauth_failed")

    access_token = result.get("access_token")
    if not access_token:
        return RedirectResponse("/?error=oauth_failed")

    # SÉCURITÉ : même principe que Google — cookie signé mais PAS chiffré, donc
    # aucun secret applicatif (client_secret) stocké ici. access_token/refresh_token
    # sont les credentials de l'UTILISATEUR (normal pour une session OAuth), pas
    # un secret de l'application.
    request.session["credentials"] = {
        "access_token": access_token,
        "refresh_token": result.get("refresh_token"),
        "expires_at": int(time.time()) + int(result.get("expires_in", 3600)),
    }
    request.session["provider"] = "microsoft"

    # Profil via Graph /me (best-effort, comme le décodage id_token pour Google)
    try:
        profile_resp = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=GRAPH_TIMEOUT,
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()
        request.session["user_profile"] = {
            "email": profile.get("mail") or profile.get("userPrincipalName"),
            "name": profile.get("displayName"),
            # Graph expose la photo via un appel binaire séparé (/me/photo/$value) ;
            # pas de tentative pour l'instant, cohérent avec l'absence d'avatar IMAP/POP.
            "picture": None,
        }
    except requests.RequestException as e:
        print(f"[WARNING] Impossible de récupérer le profil Microsoft: {e}")
        request.session["user_profile"] = {"email": None, "name": None, "picture": None}

    return RedirectResponse("/?authenticated=true")


# ── IMAP / POP ────────────────────────────────────────────────
#
# Pas d'OAuth : identifiants directs (email + mot de passe). "imap" et "pop3"
# sont deux valeurs DISTINCTES de `provider` (pas "imap" + un sous-champ
# protocole) — nécessaire côté frontend pour traiter différemment la
# suppression POP3 (définitive, pas de corbeille) de celle d'IMAP.


def _classify_imap_pop_error(e: Exception) -> str:
    """Message utilisateur clair selon le type d'échec de connexion."""
    if isinstance(e, (imaplib.IMAP4.error, poplib.error_proto)):
        return "Identifiants refusés. Vérifiez l'adresse et le mot de passe (un mot de passe d'application est parfois requis)."
    if isinstance(e, socket.gaierror):
        return "Serveur introuvable. Vérifiez le nom d'hôte."
    if isinstance(e, (socket.timeout, TimeoutError)):
        return "Le serveur ne répond pas (délai dépassé). Vérifiez l'hôte et le port."
    if isinstance(e, ConnectionRefusedError):
        return "Connexion refusée par le serveur. Vérifiez le port."
    if isinstance(e, ssl.SSLError):
        return "Erreur TLS/SSL lors de la connexion au serveur."
    return "Impossible de se connecter à ce serveur mail."


@router.post("/imap/connect")
async def imap_connect(request: Request):
    """
    Connexion IMAP/POP par identifiants. Tente une connexion réelle
    immédiatement (échec rapide, message clair) ; en cas de succès, chiffre
    le mot de passe (security/crypto.py) et stocke la session.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": True, "message": "Corps de requête invalide."})

    email_addr = (body.get("email") or "").strip()
    password = body.get("password") or ""
    protocol = (body.get("protocol") or "imap").lower()

    if not email_addr or "@" not in email_addr:
        return JSONResponse(status_code=400, content={"error": True, "message": "Adresse email invalide."})
    if not password:
        return JSONResponse(status_code=400, content={"error": True, "message": "Mot de passe manquant."})
    if protocol not in ("imap", "pop3"):
        return JSONResponse(status_code=400, content={"error": True, "message": "Protocole non supporté."})

    preset = get_preset(email_addr) or {}

    host = body.get("host") or preset.get("imap_host" if protocol == "imap" else "pop_host")
    port = body.get("port") or preset.get("imap_port" if protocol == "imap" else "pop_port")
    smtp_host = body.get("smtp_host") or preset.get("smtp_host")
    smtp_port = body.get("smtp_port") or preset.get("smtp_port")

    if not host or not port:
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "message": "Serveur inconnu pour ce domaine — merci de préciser l'hôte et le port manuellement.",
            },
        )

    try:
        port = int(port)
        smtp_port = int(smtp_port) if smtp_port else 0
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": True, "message": "Port invalide."})

    ClientClass = ImapProviderClient if protocol == "imap" else PopProviderClient
    client = ClientClass(host, port, email_addr, password, smtp_host or "", smtp_port)

    try:
        client.verify_connection()
    except Exception as e:
        # Ne JAMAIS logger le mot de passe : certaines exceptions imaplib/poplib
        # peuvent inclure la commande complète (donc potentiellement les
        # identifiants) dans leur message — on logue seulement le type
        # d'exception, jamais `e`/`str(e)` brut.
        print(f"[WARN] Connexion {protocol.upper()} échouée pour {email_addr} ({type(e).__name__})")
        return JSONResponse(
            status_code=400,
            content={"error": True, "message": _classify_imap_pop_error(e)},
        )

    secret_key = os.getenv("SECRET_KEY") or "dev-secret-key"
    request.session["credentials"] = {
        "host": host,
        "port": port,
        "protocol": protocol,
        "username": email_addr,
        "password_enc": encrypt_secret(password, secret_key),
        "smtp_host": smtp_host or "",
        "smtp_port": smtp_port,
    }
    request.session["provider"] = protocol
    request.session["user_profile"] = {
        "email": email_addr,
        "name": email_addr.split("@")[0],
        "picture": None,
    }

    return {"ok": True}


@router.get("/imap/presets")
async def imap_presets():
    """Expose la table hôtes IMAP/POP/SMTP pour préremplir le formulaire frontend."""
    return all_presets()
