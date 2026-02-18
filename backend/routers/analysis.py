"""
MailScrub.app — Analysis Router

Route principale qui lance l'analyse et retourne les résultats
au dashboard (score, catégories, top expéditeurs, recommandations).

Utilise les vraies données Gmail si l'utilisateur est authentifié,
sinon retourne les données de démonstration.
"""

import traceback
from dataclasses import asdict

from fastapi import APIRouter, Request
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


@router.get("/analyze")
async def analyze_mailbox(request: Request):
    """
    Lance l'analyse de la boîte mail.

    Si l'utilisateur est connecté via OAuth, utilise les vraies données Gmail.
    Sinon, retourne les données de démonstration.
    """
    creds_data = request.session.get("credentials")

    if creds_data:
        try:
            service, err = _get_gmail_service(request)
            if err:
                return err

            # Analyze real emails
            result = analyzer.analyze_real(service)
            data = asdict(result)
            data["mode"] = "gmail"
            return data

        except Exception as e:
            # Log the full error for debugging
            print(f"[ERROR] Gmail API failed: {e}")
            traceback.print_exc()

            # Return a clear error with fallback suggestion
            return JSONResponse(
                status_code=500,
                content={
                    "error": True,
                    "message": f"Erreur API Gmail: {str(e)}",
                    "fallback": "demo",
                },
            )
    else:
        # Fallback to demo data
        result = analyzer.analyze_demo()
        data = asdict(result)
        data["mode"] = "demo"
        return data


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

