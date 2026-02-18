"""
MailScrub.app — Analysis Router

Route principale qui lance l'analyse et retourne les résultats
au dashboard (score, catégories, top expéditeurs, recommandations).

Utilise les vraies données Gmail si l'utilisateur est authentifié,
sinon retourne les données de démonstration.
"""

import traceback
from dataclasses import asdict

import urllib.request
import urllib.error
import ssl
from email.message import EmailMessage
import base64

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from backend.src.services.analyzer import MailAnalyzer

router = APIRouter(prefix="/api", tags=["analysis"])

analyzer = MailAnalyzer()


def _get_gmail_service(request: Request):
    """
    Build a Gmail API service from session credentials.
    Returns (service, error_response) — if error_response is not None, return it.
    """
    creds_data = request.session.get("credentials")
    if not creds_data:
        return None, JSONResponse(
            status_code=401,
            content={"error": True, "message": "Non authentifié. Connectez-vous d'abord."},
        )

    # Check for stale session with old OAuth scope
    REQUIRED_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
    session_scopes = creds_data.get("scopes", [])
    if REQUIRED_SCOPE not in session_scopes:
        # Clear stale session — user needs to re-login with new scope
        request.session.pop("credentials", None)
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

    credentials = Credentials(
        token=creds_data["token"],
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data["token_uri"],
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        scopes=creds_data["scopes"],
    )

    service = build("gmail", "v1", credentials=credentials)
    return service, None


import json
from starlette.concurrency import iterate_in_threadpool
from fastapi.responses import StreamingResponse

@router.get("/analyze")
async def analyze_mailbox(request: Request, limit: int = 1000):
    """
    Lance l'analyse de la boîte mail.
    Retourne un stream NDJSON avec la progression puis le résultat.
    """
    creds_data = request.session.get("credentials")
    
    # Prépare le générateur (sync) approprié
    generator = None

    if creds_data:
        try:
            service, err = _get_gmail_service(request)
            if err:
                return err

            # Analyze real emails (returns a generator)
            generator = analyzer.analyze_real(service, limit=limit)

        except Exception as e:
            print(f"[ERROR] Gmail API failed: {e}")
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={
                    "error": True, 
                    "message": f"Erreur API Gmail: {str(e)}", 
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
    service, err = _get_gmail_service(request)
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

        deleted = 0
        errors = 0

        for msg_id in message_ids:
            try:
                if mode == "delete":
                    service.users().messages().delete(
                        userId="me", id=msg_id
                    ).execute()
                else:
                    service.users().messages().trash(
                        userId="me", id=msg_id
                    ).execute()
                deleted += 1
            except Exception as e:
                print(f"[WARN] Failed to {mode} message {msg_id}: {e}")
                errors += 1

        return {
            "deleted": deleted,
            "errors": errors,
            "mode": mode,
            "message": f"{deleted} mail(s) {'mis à la corbeille' if mode == 'trash' else 'supprimé(s) définitivement'}.",
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
    """
    Tente de se désabonner automatiquement.
    - Si mailto: envoie un mail.
    - Si http: visite le lien (GET).
    """
    service, err = _get_gmail_service(request)
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
                import urllib.parse
                subject = urllib.parse.unquote(subject)

            # Create message
            message = EmailMessage()
            message.set_content("Please unsubscribe me.")
            message["To"] = target_email
            message["From"] = "me"
            message["Subject"] = subject

            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            create_message = {"raw": encoded_message}
            service.users().messages().send(userId="me", body=create_message).execute()
            
            return {"success": True, "method": "email", "message": "Email de désabonnement envoyé."}

        # CAS 2: HTTP
        elif link.startswith("http"):
            try:
                # User-Agent standard pour ne pas être bloqué
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                req = urllib.request.Request(link, headers=headers)
                
                # Ignore SSL errors (fixes many false negatives)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
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
