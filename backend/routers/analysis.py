"""
MailScrub.app — Analysis Router

Route principale qui lance l'analyse et retourne les résultats
au dashboard (score, catégories, top expéditeurs, recommandations).

Utilise les vraies données du provider connecté (Google, Microsoft, IMAP,
POP3) si l'utilisateur est authentifié, sinon retourne les données de
démonstration.
"""

import os
import socket
import ipaddress
import time
import traceback
from dataclasses import asdict

import urllib.request
import urllib.error
import urllib.parse

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from backend.src.services.analyzer import MailAnalyzer
from backend.src.providers.base import MailProviderClient
from backend.src.providers.google_provider import GoogleProviderClient
from backend.src.providers.microsoft_provider import MICROSOFT_SCOPES, MicrosoftProviderClient, get_msal_app
from backend.src.providers.imap_provider import ImapProviderClient
from backend.src.providers.pop_provider import PopProviderClient
from backend.src.security.crypto import decrypt_secret

router = APIRouter(prefix="/api", tags=["analysis"])

analyzer = MailAnalyzer()


def _is_safe_public_url(url: str) -> bool:
    """
    Protection SSRF : n'autorise que http(s) vers une IP publique.
    Bloque loopback / IP privées / link-local / réservées (services internes,
    serveur de métadonnées cloud, etc.).

    Note : un risque résiduel de DNS-rebinding subsiste (TOCTOU entre la
    résolution et la requête réelle), acceptable pour cet usage de désabonnement.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.hostname
    if not host:
        return False

    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False

    return True


def _get_google_provider_client(request: Request, creds_data: dict):
    """Construit un GoogleProviderClient à partir des credentials Google en session."""
    REQUIRED_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
    session_scopes = creds_data.get("scopes", [])
    if REQUIRED_SCOPE not in session_scopes:
        # Session périmée (ancien scope) — l'utilisateur doit se reconnecter.
        request.session.pop("credentials", None)
        request.session.pop("provider", None)
        return None, JSONResponse(
            status_code=401,
            content={
                "error": True,
                "message": "Session expirée. Reconnectez-vous pour activer les nouvelles fonctionnalités.",
                "reauth": True,
            },
        )

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    # client_id / client_secret ne sont plus stockés en session (le cookie
    # n'est pas chiffré) : on les ré-injecte depuis l'environnement serveur.
    credentials = Credentials(
        token=creds_data["token"],
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data["token_uri"],
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=creds_data["scopes"],
    )

    service = build("gmail", "v1", credentials=credentials)
    return GoogleProviderClient(service), None


def _get_microsoft_provider_client(request: Request, creds_data: dict):
    """
    Construit un MicrosoftProviderClient, en rafraîchissant l'access token via
    MSAL s'il expire dans moins de 5 minutes (Graph n'a pas d'équivalent au
    rafraîchissement automatique de google-auth — on le gère nous-mêmes).
    """
    access_token = creds_data.get("access_token")
    expires_at = creds_data.get("expires_at", 0)

    if access_token and time.time() < expires_at - 300:
        return MicrosoftProviderClient(access_token), None

    refresh_token = creds_data.get("refresh_token")
    if not refresh_token:
        request.session.pop("credentials", None)
        request.session.pop("provider", None)
        return None, JSONResponse(
            status_code=401,
            content={
                "error": True,
                "message": "Session Microsoft expirée. Reconnectez-vous.",
                "reauth": True,
            },
        )

    msal_app = get_msal_app()
    result = msal_app.acquire_token_by_refresh_token(refresh_token, scopes=MICROSOFT_SCOPES)

    if "error" in result or "access_token" not in result:
        print(f"[WARN] Rafraîchissement du token Microsoft échoué : {result.get('error_description', result.get('error'))}")
        request.session.pop("credentials", None)
        request.session.pop("provider", None)
        return None, JSONResponse(
            status_code=401,
            content={
                "error": True,
                "message": "Session Microsoft expirée. Reconnectez-vous.",
                "reauth": True,
            },
        )

    access_token = result["access_token"]
    request.session["credentials"] = {
        "access_token": access_token,
        "refresh_token": result.get("refresh_token", refresh_token),
        "expires_at": int(time.time()) + int(result.get("expires_in", 3600)),
    }
    return MicrosoftProviderClient(access_token), None


def _get_imap_pop_provider_client(request: Request, creds_data: dict, provider_name: str):
    """Reconstruit un Imap/PopProviderClient — déchiffre le mot de passe stocké en session."""
    secret_key = os.getenv("SECRET_KEY") or "dev-secret-key"
    try:
        password = decrypt_secret(creds_data["password_enc"], secret_key)
    except (ValueError, KeyError):
        request.session.pop("credentials", None)
        request.session.pop("provider", None)
        return None, JSONResponse(
            status_code=401,
            content={"error": True, "message": "Session invalide. Reconnectez-vous.", "reauth": True},
        )

    ClientClass = ImapProviderClient if provider_name == "imap" else PopProviderClient
    client = ClientClass(
        host=creds_data["host"],
        port=creds_data["port"],
        username=creds_data["username"],
        password=password,
        smtp_host=creds_data.get("smtp_host", ""),
        smtp_port=creds_data.get("smtp_port", 0),
    )
    return client, None


def _get_provider_client(request: Request):
    """
    Construit un MailProviderClient à partir de la session (quel que soit le
    provider connecté). Returns (client, error_response) — si error_response
    n'est pas None, le renvoyer tel quel.
    """
    creds_data = request.session.get("credentials")
    if not creds_data:
        return None, JSONResponse(
            status_code=401,
            content={"error": True, "message": "Non authentifié. Connectez-vous d'abord."},
        )

    # Compat : une session créée avant l'introduction du champ "provider" a des
    # credentials Google mais pas cette clé (voir auth.py::auth_status).
    provider_name = request.session.get("provider") or "google"

    if provider_name == "google":
        return _get_google_provider_client(request, creds_data)
    if provider_name == "microsoft":
        return _get_microsoft_provider_client(request, creds_data)
    if provider_name in ("imap", "pop3"):
        return _get_imap_pop_provider_client(request, creds_data, provider_name)

    return None, JSONResponse(
        status_code=501,
        content={"error": True, "message": f"Provider '{provider_name}' non supporté pour le moment."},
    )


import json
from starlette.concurrency import iterate_in_threadpool
from fastapi.responses import StreamingResponse

@router.get("/analyze")
async def analyze_mailbox(request: Request, limit: int = 1000):
    """
    Lance l'analyse de la boîte mail.
    Retourne un stream NDJSON avec la progression puis le résultat.
    """
    # Borne le volume demandé (évite des scans abusifs / coûteux via ?limit=...).
    limit = max(1, min(limit, 5000))

    creds_data = request.session.get("credentials")

    # Prépare le générateur (sync) approprié
    generator = None

    if creds_data:
        try:
            provider_client, err = _get_provider_client(request)
            if err:
                return err

            # Analyze real emails (returns a generator)
            generator = analyzer.analyze_real(provider_client, limit=limit)

        except Exception as e:
            print(f"[ERROR] Provider API failed: {e}")
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={
                    "error": True,
                    "message": f"Erreur API: {str(e)}",
                    "fallback": "demo"
                }
            )
    else:
        # Fallback to demo data
        generator = analyzer.analyze_demo()

    # Wrapper async pour streamer le générateur sync sans bloquer
    async def event_generator():
        try:
            async for item in iterate_in_threadpool(generator):
                yield json.dumps(item) + "\n"
        except Exception as e:
            print(f"[ERROR] Stream failed: {e}")
            traceback.print_exc()
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@router.post("/delete")
async def delete_emails(request: Request):
    """
    Supprime (corbeille ou définitif) les mails par leurs IDs.

    Body JSON:
        - message_ids: list[str] — IDs des messages à supprimer
        - mode: "trash" (défaut) ou "delete" (définitif)

    Retourne le nombre de mails supprimés et l'espace libéré estimé.
    """
    provider_client, err = _get_provider_client(request)
    if err:
        return err

    try:
        body = await request.json()
        message_ids = body.get("message_ids", [])
        mode = body.get("mode", "trash")

        if not message_ids:
            return JSONResponse(
                status_code=400,
                content={"error": True, "message": "Aucun message à supprimer."},
            )

        result = provider_client.delete_messages(message_ids, mode)

        return {
            "deleted": result.deleted,
            "errors": result.errors,
            "mode": mode,
            "message": f"{result.deleted} mail(s) {'mis à la corbeille' if mode == 'trash' else 'supprimé(s) définitivement'}.",
        }

    except Exception as e:
        print(f"[ERROR] Delete failed: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": True, "message": f"Erreur suppression: {str(e)}"},
        )

@router.post("/unsubscribe")
async def unsubscribe(request: Request):
    """Tente un désabonnement automatique à partir d'un lien `List-Unsubscribe`.

    Corps attendu : ``{"email": str, "link": str}`` (le lien est déjà extrait côté
    frontend depuis l'en-tête, sous forme `https://…` ou `mailto:…`).

    Comportement :
      - **mailto:** → envoie un e-mail de désabonnement via le provider connecté.
      - **http(s):** → garde SSRF (`_is_safe_public_url`) puis GET côté serveur, TLS vérifié,
        timeout 10 s. ``2xx`` ⇒ ``{"success": true}`` ; sinon/exception ⇒ ``{"fallback": true}``
        (l'UI ouvre alors le lien pour une action manuelle — beaucoup de services refusent le
        GET automatisé en 403/405/timeout).

    ⚠️ Ne JAMAIS faire d'`import` local d'un module ici : un `import` dans une branche rend la
    cible locale à toute la fonction (UnboundLocalError dans les autres branches). Tous les
    imports `urllib.*` sont au niveau module.
    """
    provider_client, err = _get_provider_client(request)
    if err:
        return err

    try:
        body = await request.json()
        link = body.get("link", "")
        email_addr = body.get("email", "")

        if not link:
            return JSONResponse(status_code=400, content={"error": True, "message": "Lien manquant"})

        # CAS 1: Mailto
        if "mailto:" in link:
            # Format: mailto:unsubscribe@dom.com?subject=Unsubscribe
            # Basic parsing
            clean_link = link.replace("mailto:", "").strip()
            target_email = clean_link.split("?")[0]

            subject = "Unsubscribe"
            if "subject=" in link:
                subject = link.split("subject=")[1].split("&")[0]
                # urllib.parse est déjà importé au niveau module. Un `import` local ici
                # ferait de `urllib` une variable locale à TOUTE la fonction (Python),
                # provoquant un UnboundLocalError dans la branche HTTP plus bas.
                subject = urllib.parse.unquote(subject)

            provider_client.send_unsubscribe_mailto(target_email, subject)

            return {"success": True, "method": "email", "message": "Email de désabonnement envoyé."}

        # CAS 2: HTTP
        elif link.startswith("http"):
            # Protection SSRF : refuser les URLs internes/privées.
            if not _is_safe_public_url(link):
                return JSONResponse(
                    status_code=400,
                    content={"error": True, "message": "Lien de désabonnement non autorisé."},
                )
            try:
                # User-Agent standard pour ne pas être bloqué
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                req = urllib.request.Request(link, headers=headers)

                # TLS vérifié (on NE désactive PAS la validation des certificats).
                with urllib.request.urlopen(req, timeout=10) as response:
                    code = response.getcode()
                    if 200 <= code < 300:
                        return {"success": True, "method": "http", "message": "Lien visité avec succès."}
                    else:
                        return JSONResponse(
                            status_code=400,
                            content={"error": True, "method": "http", "message": f"Le lien a renvoyé le code {code}", "fallback": True}
                        )
            except Exception as e:
                print(f"[WARN] HTTP Unsubscribe failed: {e}")
                return JSONResponse(
                    status_code=400,
                    content={"error": True, "method": "http", "message": "Impossible d'accéder au lien automatiquement.", "fallback": True}
                )

        else:
             return JSONResponse(status_code=400, content={"error": True, "message": "Type de lien non supporté"})

    except Exception as e:
        print(f"[ERROR] Unsubscribe failed: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": True, "message": f"Erreur serveur: {str(e)}"},
        )
